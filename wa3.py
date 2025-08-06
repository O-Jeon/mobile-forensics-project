import os
import glob
import sqlite3
import subprocess
import shutil
import sys
import tempfile

def mount_img(img_path, mount_point):
    if not os.path.isfile(img_path):
        raise FileNotFoundError(f"[오류] 이미지 파일이 존재하지 않습니다: {img_path}")
    os.makedirs(mount_point, exist_ok=True)
    subprocess.run(["sudo", "umount", mount_point], stderr=subprocess.DEVNULL)
    # noload 옵션 포함하여 마운트 시도
    result = subprocess.run(
        ["sudo", "mount", "-o", "loop,ro,noload", img_path, mount_point],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("[마운트 실패] mount 커맨드 출력:")
        print(result.stdout)
        print(result.stderr)
        print("mount 명령이 실패했습니다. 아래 항목을 다시 확인하세요:")
        print("- 파일 경로/파일명 맞나?")
        print("- sudo 비밀번호 맞게 입력했나?")
        print("- /home/kali/mnt 폴더 존재 권한있나?")
        print("- ext4 등 리눅스 파일시스템이 맞나? (file 명령 활용)")
        print("- dmesg | tail -30 명령으로 커널 에러 확인")
        raise RuntimeError("mount 실패! noload 사용에도 마운트 불가. 위 경고를 참고하세요.")
    print(f"[+] 마운트 완료: {mount_point}")

def umount_img(mount_point):
    subprocess.run(["sudo", "umount", mount_point], stderr=subprocess.DEVNULL)
    print(f"[+] 마운트 해제: {mount_point}")

def copy_db_with_sudo(src_db_path, temp_dir):
    """sudo로 DB 파일을 임시 디렉토리에 복사하고 읽을 수 있게 권한 변경"""
    try:
        db_name = os.path.basename(src_db_path)
        temp_db_path = os.path.join(temp_dir, db_name)
        
        # sudo로 파일 복사
        result = subprocess.run(
            ["sudo", "cp", src_db_path, temp_db_path],
            capture_output=True, text=True
        )
        
        if result.returncode != 0:
            return None
            
        # 권한 변경으로 읽을 수 있게 만들기
        subprocess.run(
            ["sudo", "chmod", "644", temp_db_path],
            capture_output=True, text=True
        )
        
        # 소유권 변경 (현재 사용자로)
        current_user = os.getenv('USER', 'kali')
        subprocess.run(
            ["sudo", "chown", f"{current_user}:{current_user}", temp_db_path],
            capture_output=True, text=True
        )
        
        return temp_db_path if os.path.exists(temp_db_path) else None
        
    except Exception as e:
        print(f"[경고] DB 복사 실패 {src_db_path}: {e}")
        return None

def get_app_categories():
    """앱을 카테고리별로 분류"""
    return {
        "messaging": {
            "apps": [
                "com.kakao.talk",           # 카카오톡
                "jp.naver.line.android",    # 라인
                "com.whatsapp",             # 왓츠앱
                "com.facebook.orca",        # 메신저
                "com.discord",              # 디스코드
                "org.telegram.messenger",   # 텔레그램
                "com.skype.raider",         # 스카이프
            ],
            "priority": 1
        },
        "social": {
            "apps": [
                "com.instagram.android",    # 인스타그램
                "com.facebook.katana",      # 페이스북
                "com.twitter.android",      # 트위터
                "com.snapchat.android",     # 스냅챗
                "com.tiktok.musically",     # 틱톡
                "com.linkedin.android",     # 링크드인
            ],
            "priority": 2
        },
        "media": {
            "apps": [
                "com.spotify.music",        # 스포티파이
                "com.netflix.mediaclient",  # 넷플릭스
                "com.youtube.android",      # 유튜브
                "com.soundcloud.android",   # SoundCloud
                "com.coffeebeanventures.easyvoicerecorder",  # 녹음앱
                "com.google.android.apps.photos",  # 구글 포토
            ],
            "priority": 2
        },
        "productivity": {
            "apps": [
                "com.google.android.keep",  # Google Keep
                "com.evernote",             # 에버노트
                "com.microsoft.office.onenote",  # 원노트
                "com.todoist",              # 투두이스트
                "com.any.do",               # Any.do
                "com.dropbox.android",      # 드롭박스
            ],
            "priority": 1
        },
        "email": {
            "apps": [
                "com.google.android.gm",    # Gmail
                "com.microsoft.office.outlook",  # 아웃룩
                "com.yahoo.mobile.client.android.mail",  # 야후 메일
            ],
            "priority": 2
        },
        "maps": {
            "apps": [
                "net.daum.android.map",     # 다음지도
                "com.google.android.apps.maps",  # 구글맵
                "com.waze",                 # 웨이즈
            ],
            "priority": 3
        },
        "system": {
            "apps": [
                "com.google.android.gms",   # Google Play Services
                "com.android.vending",      # Google Play Store
                "com.samsung",              # 삼성 앱들
                "com.sec.",                 # 삼성 시스템 앱들
                "android",                  # 시스템 앱들
            ],
            "priority": 4  # 낮은 우선순위
        }
    }

def find_database_files(mount_point):
    """개선된 DB 검색 - 서드파티 앱 우선, 다중 검색 방법 사용"""
    db_paths = []
    root_data = os.path.join(mount_point, "data")
    
    if not os.path.exists(root_data):
        print(f"[경고] /data 폴더가 존재하지 않습니다: {root_data}")
        return []
    
    print("[+] 데이터베이스 파일 검색 중...")
    print(f"[+] 검색 경로: {root_data}")
    
    app_categories = get_app_categories()
    
    # 1단계: 직접 ls를 이용한 앱 폴더 검색 (더 안정적)
    print("\n[+] 1단계: 앱 폴더 직접 검색...")
    app_folders = []
    try:
        ls_result = subprocess.run(
            ["sudo", "ls", "-la", root_data],
            capture_output=True, text=True, timeout=30
        )
        
        if ls_result.returncode == 0:
            lines = ls_result.stdout.strip().split('\n')
            
            for line in lines:
                parts = line.split()
                if len(parts) >= 9 and parts[0].startswith('d'):  # 디렉토리만
                    folder_name = parts[-1]
                    if '.' in folder_name and folder_name not in ['.', '..']:  # 패키지명 형태
                        full_path = os.path.join(root_data, folder_name)
                        app_folders.append((folder_name, full_path))
            
            print(f"[+] 발견된 앱 폴더: {len(app_folders)}개")
            
            # 카테고리별로 분류하여 출력
            categorized_apps = {cat: [] for cat in app_categories.keys()}
            uncategorized = []
            
            for app_name, folder_path in app_folders:
                categorized = False
                for category, info in app_categories.items():
                    if any(app_pattern in app_name for app_pattern in info["apps"]):
                        categorized_apps[category].append((app_name, folder_path))
                        categorized = True
                        break
                
                if not categorized:
                    uncategorized.append((app_name, folder_path))
            
            # 우선순위 순으로 출력
            sorted_categories = sorted(app_categories.items(), key=lambda x: x[1]["priority"])
            
            for category, info in sorted_categories:
                if categorized_apps[category]:
                    print(f"\n  📱 {category.upper()} ({len(categorized_apps[category])}개):")
                    for app_name, folder in categorized_apps[category]:
                        print(f"    🔥 {app_name}")
            
            if uncategorized:
                print(f"\n  📱 기타 앱 ({len(uncategorized)}개):")
                for app_name, folder in uncategorized[:15]:  # 처음 15개만 표시
                    print(f"    - {app_name}")
                if len(uncategorized) > 15:
                    print(f"    ... 및 {len(uncategorized)-15}개 더")
                    
        else:
            print(f"[경고] ls 명령 실패: {ls_result.stderr}")
            
    except Exception as e:
        print(f"[경고] 앱 폴더 검색 오류: {e}")
    
    # 2단계: 서드파티 앱 우선 DB 검색 - 개별 앱 폴더 직접 검사
    print(f"\n[+] 2단계: 서드파티 앱 우선 개별 검사...")
    
    # DB 파일 정보를 저장할 리스트
    db_info_list = []
    
    # 우선순위 앱들을 먼저 검사
    priority_apps = []
    for category, info in app_categories.items():
        if info["priority"] <= 2:  # 고우선순위만
            for app_pattern in info["apps"]:
                for app_name, folder_path in app_folders:
                    if app_pattern in app_name:
                        priority_apps.append((app_name, folder_path, category, info["priority"]))
    
    print(f"  우선 검사할 서드파티 앱: {len(priority_apps)}개")
    
    # 우선순위 앱들 개별 검사
    for app_name, app_path, category, priority in priority_apps:
        print(f"    🔍 {app_name} 개별 검사...")
        
        # databases 폴더 직접 확인
        databases_path = os.path.join(app_path, "databases")
        try:
            ls_db_result = subprocess.run(
                ["sudo", "ls", "-la", databases_path],
                capture_output=True, text=True, timeout=10
            )
            
            if ls_db_result.returncode == 0:
                print(f"      ✓ databases 폴더 발견")
                lines = ls_db_result.stdout.strip().split('\n')
                db_count = 0
                
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 9 and not parts[0].startswith('d'):  # 파일만
                        filename = parts[-1]
                        if filename.endswith('.db') and filename not in ['.', '..']:
                            db_file_path = os.path.join(databases_path, filename)
                            
                            # 파일 크기 확인
                            try:
                                stat_result = subprocess.run(
                                    ["sudo", "stat", "-c", "%s", db_file_path],
                                    capture_output=True, text=True, timeout=5
                                )
                                size_bytes = int(stat_result.stdout.strip()) if stat_result.returncode == 0 else 0
                            except:
                                size_bytes = 0
                            
                            db_info_list.append({
                                "path": db_file_path,
                                "app_name": app_name,
                                "db_name": filename,
                                "size_bytes": size_bytes,
                                "category": category,
                                "priority": priority
                            })
                            
                            db_count += 1
                            print(f"        🗃️  {filename} ({size_bytes} bytes)")
                
                if db_count == 0:
                    print(f"      ⚠️  databases 폴더가 비어있음")
            else:
                print(f"      ❌ databases 폴더 없음")
                
                # databases 폴더가 없으면 다른 가능한 위치들 검사
                possible_paths = [
                    os.path.join(app_path, "files"),
                    os.path.join(app_path, "shared_prefs"),
                    app_path  # 앱 루트 폴더
                ]
                
                for check_path in possible_paths:
                    try:
                        find_result = subprocess.run(
                            ["sudo", "find", check_path, "-name", "*.db", "-type", "f", "-maxdepth", "2"],
                            capture_output=True, text=True, timeout=10
                        )
                        
                        if find_result.returncode == 0 and find_result.stdout.strip():
                            found_dbs = find_result.stdout.strip().split('\n')
                            for db_file in found_dbs:
                                if db_file and os.path.exists(db_file):
                                    # 파일 크기 확인
                                    try:
                                        stat_result = subprocess.run(
                                            ["sudo", "stat", "-c", "%s", db_file],
                                            capture_output=True, text=True, timeout=5
                                        )
                                        size_bytes = int(stat_result.stdout.strip()) if stat_result.returncode == 0 else 0
                                    except:
                                        size_bytes = 0
                                    
                                    db_info_list.append({
                                        "path": db_file,
                                        "app_name": app_name,
                                        "db_name": os.path.basename(db_file),
                                        "size_bytes": size_bytes,
                                        "category": category,
                                        "priority": priority
                                    })
                                    
                                    rel_path = os.path.relpath(db_file, app_path)
                                    print(f"        🗃️  {rel_path} ({size_bytes} bytes)")
                            break
                    except:
                        continue
                        
        except Exception as e:
            print(f"      ❌ 검사 실패: {e}")
    
    # 3단계: 전체 find 검색 (시스템 앱 포함)
    print(f"\n[+] 3단계: 전체 시스템 DB 파일 검색...")
    try:
        # 방법 1: databases 폴더 검색
        find_db_folders_cmd = [
            "sudo", "find", root_data,
            "-type", "d",
            "-name", "databases",
            "-maxdepth", "4"
        ]
        
        result = subprocess.run(find_db_folders_cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and result.stdout.strip():
            databases_folders = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
            print(f"    발견된 databases 폴더: {len(databases_folders)}개")
            
            for db_folder in databases_folders:
                if os.path.exists(db_folder):
                    rel_path = os.path.relpath(db_folder, root_data)
                    app_name = rel_path.split('/')[0]
                    
                    # 이미 처리된 앱인지 확인
                    already_processed = any(db["app_name"] == app_name for db in db_info_list)
                    if already_processed:
                        continue
                    
                    try:
                        # ls로 DB 파일 검색
                        ls_db_result = subprocess.run(
                            ["sudo", "ls", "-la", db_folder],
                            capture_output=True, text=True, timeout=10
                        )
                        
                        if ls_db_result.returncode == 0:
                            lines = ls_db_result.stdout.strip().split('\n')
                            for line in lines:
                                parts = line.split()
                                if len(parts) >= 9 and not parts[0].startswith('d'):  # 파일만
                                    filename = parts[-1]
                                    if filename.endswith('.db') and filename not in ['.', '..']:
                                        db_file_path = os.path.join(db_folder, filename)
                                        
                                        # 파일 크기 확인
                                        try:
                                            stat_result = subprocess.run(
                                                ["sudo", "stat", "-c", "%s", db_file_path],
                                                capture_output=True, text=True, timeout=5
                                            )
                                            size_bytes = int(stat_result.stdout.strip()) if stat_result.returncode == 0 else 0
                                        except:
                                            size_bytes = 0
                                        
                                        # 앱 카테고리 확인
                                        category = "uncategorized"
                                        priority = 5
                                        
                                        for cat, info in app_categories.items():
                                            if any(app_pattern in app_name for app_pattern in info["apps"]):
                                                category = cat
                                                priority = info["priority"]
                                                break
                                        
                                        db_info_list.append({
                                            "path": db_file_path,
                                            "app_name": app_name,
                                            "db_name": filename,
                                            "size_bytes": size_bytes,
                                            "category": category,
                                            "priority": priority
                                        })
                                        
                    except subprocess.TimeoutExpired:
                        print(f"      ? {app_name}: DB 검색 타임아웃")
                    except Exception as e:
                        print(f"      ? {app_name}: DB 검색 실패 ({e})")
        
        # 우선순위 기준으로 정렬 (서드파티 앱 우선)
        db_info_list.sort(key=lambda x: (x["priority"], -x["size_bytes"]))
        
        # 결과 출력 및 경로 리스트 생성
        if db_info_list:
            print(f"\n[+] DB 파일 분석 우선순위:")
            current_category = None
            
            for db_info in db_info_list:
                if db_info["category"] != current_category:
                    current_category = db_info["category"]
                    print(f"\n  📊 {current_category.upper()}:")
                
                size_kb = db_info["size_bytes"] / 1024 if db_info["size_bytes"] > 0 else 0
                marker = "🔥" if db_info["priority"] <= 2 else "  "
                print(f"{marker} {db_info['app_name']}/{db_info['db_name']} ({size_kb:.1f} KB)")
                
                db_paths.append(db_info["path"])
            
            # 통계 출력
            total_size = sum(db["size_bytes"] for db in db_info_list)
            high_priority_count = sum(1 for db in db_info_list if db["priority"] <= 2)
            
            print(f"\n[+] 총 {len(db_info_list)}개 DB 파일 발견")
            print(f"[+] 총 DB 파일 크기: {total_size / 1024 / 1024:.2f} MB")
            print(f"[+] 고우선순위 서드파티 앱 DB: {high_priority_count}개 ⭐")
        else:
            print(f"[경고] DB 파일을 찾을 수 없습니다")
            
    except Exception as e:
        print(f"[경고] DB 파일 검색 오류: {e}")
    
    return db_paths

def get_important_tables_by_app(app_name):
    """앱별로 중요한 테이블명 패턴 반환"""
    table_patterns = {
        "com.kakao.talk": ["chat", "message", "friend", "room", "OpenChatRoom"],
        "jp.naver.line.android": ["chat", "message", "contact", "room", "group"],
        "com.whatsapp": ["messages", "chat", "contacts", "group"],
        "com.google.android.keep": ["note", "list", "reminder", "label"],
        "com.coffeebeanventures.easyvoicerecorder": ["recording", "voice", "audio"],
        "com.instagram.android": ["user", "media", "story", "direct"],
        "com.spotify.music": ["track", "playlist", "user", "offline"],
        "com.netflix.mediaclient": ["profile", "viewing", "download"],
        "com.google.android.gm": ["message", "conversation", "label", "attachment"],
        "com.evernote": ["note", "notebook", "tag", "resource"],
        "com.dropbox.android": ["file", "sync", "account"],
    }
    
    # 패턴 매칭으로 앱 찾기
    for app_pattern, patterns in table_patterns.items():
        if app_pattern in app_name:
            return patterns
    
    return None  # 모든 테이블 분석

def analyze_sqlite_db(db_path, app_name=None, row_limit=10, temp_dir=None):
    """개선된 DB 분석 - 앱별 중요 테이블 우선, 한글 데이터 최우선"""
    summary = []
    copied_db = None
    
    try:
        # DB 파일을 임시 디렉토리에 복사
        if temp_dir:
            copied_db = copy_db_with_sudo(db_path, temp_dir)
            if not copied_db:
                return [{"table": "COPY_ERROR", "columns": [], "rows": [f"파일 복사 실패: {db_path}"]}]
            working_db = copied_db
        else:
            working_db = db_path
        
        conn = sqlite3.connect(working_db)
        cur = conn.cursor()
        
        # 테이블 목록 가져오기
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        all_tables = [r[0] for r in cur.fetchall()]
        
        # 앱별 중요 테이블 패턴 가져오기
        important_patterns = get_important_tables_by_app(app_name) if app_name else None
        
        # 테이블 우선순위 정렬
        if important_patterns:
            important_tables = []
            other_tables = []
            
            for table in all_tables:
                is_important = any(pattern.lower() in table.lower() for pattern in important_patterns)
                if is_important:
                    important_tables.append(table)
                else:
                    other_tables.append(table)
            
            # 중요한 테이블을 먼저, 나머지는 뒤에
            table_names = important_tables + other_tables
            print(f"    📋 중요 테이블: {len(important_tables)}개, 기타: {len(other_tables)}개")
        else:
            table_names = all_tables
            print(f"    📋 전체 테이블: {len(all_tables)}개")
        
        for table in table_names:
            try:
                # 테이블 스키마 정보
                cur.execute(f"PRAGMA table_info({table});")
                columns = [c[1] for c in cur.fetchall()]
                
                # 행 개수 확인
                cur.execute(f"SELECT COUNT(*) FROM {table};")
                row_count = cur.fetchone()[0]
                
                # 데이터 샘플
                cur.execute(f"SELECT * FROM {table} LIMIT {row_limit};")
                rows = cur.fetchall()

                # 한글 및 이메일 포함 여부 판단
                has_korean = False
                has_email = False
                korean_count = 0
                email_count = 0
                
                if rows:
                    for row in rows:
                        for col in row:
                            if isinstance(col, str):
                                # 한글 유니코드 범위 검사 (가-힣, ㄱ-ㅎ, ㅏ-ㅣ)
                                korean_chars = sum(1 for char in col if '\uac00' <= char <= '\ud7a3' or '\u1100' <= char <= '\u11ff' or '\u3130' <= char <= '\u318f')
                                if korean_chars > 0:
                                    has_korean = True
                                    korean_count += korean_chars
                                
                                # 이메일 패턴 검사
                                import re
                                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                                emails = re.findall(email_pattern, col)
                                if emails:
                                    has_email = True
                                    email_count += len(emails)
                
                # 포렌식적으로 의미없는 테이블 필터링 (더 엄격하게)
                forensic_irrelevant_patterns = [
                    'cache', 'temp', 'tmp', 'log', 'debug', 'analytics', 'crash',
                    'session', 'preference', 'config', 'setting', 'metadata',
                    'index', 'fts', 'search', 'sync', 'backup', 'trash',
                    'android_', 'sqlite_', 'room_', 'dagger_', 'hilt_',
                    'overrides', 'saved_secure', 'saved_global', 'secure',
                    'system', 'global', 'default', 'properties', 'flags',
                    'state', 'status', 'info', 'data', 'values', 'settings'
                ]
                
                is_forensic_irrelevant = any(pattern in table.lower() for pattern in forensic_irrelevant_patterns)
                
                # 중요한 테이블인지 표시
                is_important = False
                if important_patterns:
                    is_important = any(pattern.lower() in table.lower() for pattern in important_patterns)
                
                # 포렌식 우선순위 계산 (한글/이메일 > 중요 > 기타 > 무관)
                forensic_priority = 0
                if has_korean or has_email:
                    forensic_priority = 3  # 최우선 (한글 또는 이메일)
                elif is_important:
                    forensic_priority = 2  # 고우선순위
                elif not is_forensic_irrelevant:
                    forensic_priority = 1  # 일반
                else:
                    forensic_priority = 0  # 무관
                
                summary.append({
                    "table": table, 
                    "columns": columns, 
                    "rows": rows,
                    "row_count": row_count,
                    "is_important": is_important,
                    "has_korean": has_korean,
                    "has_email": has_email,
                    "korean_count": korean_count,
                    "email_count": email_count,
                    "is_forensic_irrelevant": is_forensic_irrelevant,
                    "forensic_priority": forensic_priority
                })
                
            except Exception as table_error:
                summary.append({
                    "table": table, 
                    "columns": [], 
                    "rows": [f"테이블 분석 오류: {str(table_error)}"],
                    "row_count": 0,
                    "is_important": False,
                    "has_korean": False,
                    "has_email": False,
                    "korean_count": 0,
                    "email_count": 0,
                    "is_forensic_irrelevant": False,
                    "forensic_priority": 0
                })
                
    except Exception as e:
        summary.append({
            "table": "DB_ERROR", 
            "columns": [], 
            "rows": [f"DB 연결 오류: {str(e)}"],
            "row_count": 0,
            "is_important": False,
            "has_korean": False,
            "has_email": False,
            "korean_count": 0,
            "email_count": 0,
            "is_forensic_irrelevant": False,
            "forensic_priority": 0
        })
    finally:
        try: 
            conn.close()
        except: 
            pass
            
        # 임시 복사본 정리
        if copied_db and os.path.exists(copied_db):
            try:
                os.remove(copied_db)
            except:
                pass
    
    return summary

def generate_markdown_report(db_summaries, output_path, mount_point):
    """개선된 마크다운 보고서 생성 - 포렌식적으로 의미있는 데이터만 포함, 한글 데이터 최우선"""
    app_categories = get_app_categories()
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Wear OS 서드파티 앱 DB 아티팩트 분석 리포트\n\n")
        f.write("이 보고서는 **포렌식적으로 의미있는** 서드파티 앱의 데이터베이스 테이블만을 분석한 결과입니다.\n")
        f.write("**한글 데이터와 이메일 주소가 포함된 테이블만 표시됩니다.**\n\n")
        
        # 요약 섹션
        f.write("## 📊 분석 요약\n\n")
        total_dbs = len(db_summaries)
        
        # 통계 계산
        total_tables = 0
        tables_with_data = 0
        total_rows = 0
        korean_tables = 0
        email_tables = 0
        forensic_relevant_tables = 0
        
        for db_file, tables in db_summaries.items():
            for table_info in tables:
                if table_info.get('table') not in ['DB_ERROR', 'COPY_ERROR']:
                    total_tables += 1
                    row_count = table_info.get('row_count', 0)
                    if row_count > 0:
                        tables_with_data += 1
                        total_rows += row_count
                        
                        # 포렌식 관련성 및 한글/이메일 데이터 통계
                        if table_info.get('has_korean', False):
                            korean_tables += 1
                        if table_info.get('has_email', False):
                            email_tables += 1
                        if table_info.get('forensic_priority', 0) > 0:
                            forensic_relevant_tables += 1
        
        # 카테고리별 통계
        category_stats = {}
        for db_file, tables in db_summaries.items():
            rel_path = os.path.relpath(db_file, os.path.join(mount_point, "data"))
            app_name = rel_path.split('/')[0]
            
            category = "기타"
            for cat, info in app_categories.items():
                if any(app_pattern in app_name for app_pattern in info["apps"]):
                    category = cat
                    break
            
            if category not in category_stats:
                category_stats[category] = 0
            category_stats[category] += 1
        
        f.write(f"- **총 분석된 DB 파일**: {total_dbs}개\n")
        f.write(f"- **총 테이블 수**: {total_tables}개\n")
        f.write(f"- **데이터가 있는 테이블**: {tables_with_data}개 ({tables_with_data/total_tables*100:.1f}%)\n")
        f.write(f"- **포렌식 관련 테이블**: {forensic_relevant_tables}개 ⭐\n")
        f.write(f"- **한글 데이터 포함 테이블**: {korean_tables}개 🇰🇷\n")
        f.write(f"- **이메일 주소 포함 테이블**: {email_tables}개 📧\n")
        f.write(f"- **총 데이터 레코드**: {total_rows:,}개\n\n")
        
        for category, count in sorted(category_stats.items()):
            f.write(f"- **{category.title()}**: {count}개 DB\n")
        f.write("\n")
        
        # 카테고리별로 정렬해서 출력
        categorized_dbs = {}
        for db_file, tables in db_summaries.items():
            rel_path = os.path.relpath(db_file, os.path.join(mount_point, "data"))
            app_name = rel_path.split('/')[0]
            
            category = "기타"
            priority = 5
            for cat, info in app_categories.items():
                if any(app_pattern in app_name for app_pattern in info["apps"]):
                    category = cat
                    priority = info["priority"]
                    break
            
            if category not in categorized_dbs:
                categorized_dbs[category] = []
            categorized_dbs[category].append((db_file, tables, priority))
        
        # 우선순위 순으로 카테고리 정렬
        sorted_categories = sorted(categorized_dbs.items(), 
                                 key=lambda x: min(item[2] for item in x[1]))
        
        for category, db_list in sorted_categories:
            f.write(f"## 📱 {category.title()} 앱\n\n")
            
            # 해당 카테고리 내에서도 우선순위 정렬
            sorted_db_list = sorted(db_list, key=lambda x: x[2])
            
            for db_file, tables, priority in sorted_db_list:
                rel_db_path = os.path.relpath(db_file, os.path.join(mount_point, "data"))
                app_name = rel_db_path.split('/')[0]
                
                # 한글/이메일 데이터가 있는 테이블들만 필터링
                korean_tables_with_data = []
                email_tables_with_data = []
                other_relevant_tables = []
                
                for table_info in tables:
                    # 오류 테이블이거나 데이터가 없는 테이블은 건너뛰기
                    if table_info.get('table') in ['DB_ERROR', 'COPY_ERROR']:
                        continue
                    
                    row_count = table_info.get('row_count', 0)
                    has_data = row_count > 0
                    forensic_priority = table_info.get('forensic_priority', 0)
                    
                    # 한글/이메일 데이터가 없는 테이블은 제외
                    if not has_data or not (table_info.get('has_korean', False) or table_info.get('has_email', False)):
                        continue
                    
                    if table_info.get('has_korean', False):
                        korean_tables_with_data.append(table_info)
                    elif table_info.get('has_email', False):
                        email_tables_with_data.append(table_info)
                    else:
                        other_relevant_tables.append(table_info)
                
                # 한글/이메일 데이터가 있는 테이블이 하나도 없으면 이 DB는 건너뛰기
                if not korean_tables_with_data and not email_tables_with_data and not other_relevant_tables:
                    continue
                
                # 우선순위 표시
                priority_marker = {1: "🔥 고우선순위", 2: "⭐ 중우선순위", 3: "📍 저우선순위"}.get(priority, "")
                
                f.write(f"### {priority_marker} `/data/{rel_db_path}`\n\n")
                f.write(f"**앱**: `{app_name}`\n")
                
                # 테이블 통계 표시
                total_relevant_tables = len(korean_tables_with_data) + len(email_tables_with_data) + len(other_relevant_tables)
                total_rows_in_db = sum(t.get('row_count', 0) for t in korean_tables_with_data + email_tables_with_data + other_relevant_tables)
                f.write(f"**한글/이메일 데이터 테이블**: {total_relevant_tables}개 ({total_rows_in_db:,}행)\n")
                
                if korean_tables_with_data:
                    f.write(f"**한글 데이터 테이블**: {len(korean_tables_with_data)}개 🇰🇷\n")
                if email_tables_with_data:
                    f.write(f"**이메일 데이터 테이블**: {len(email_tables_with_data)}개 📧\n")
                f.write("\n")
                
                # 한글 데이터 테이블을 최우선으로 표시
                if korean_tables_with_data:
                    f.write("#### 🇰🇷 한글 데이터 테이블\n\n")
                    for info in korean_tables_with_data:
                        write_table_info(f, info, is_korean=True)
                
                # 이메일 데이터 테이블 표시
                if email_tables_with_data:
                    f.write("#### 📧 이메일 데이터 테이블\n\n")
                    for info in email_tables_with_data:
                        write_table_info(f, info, is_email=True)
                
                f.write("---\n\n")

def write_table_info(f, info, is_korean=False, is_email=False):
    """테이블 정보를 마크다운으로 작성 - 한글/이메일 데이터가 있는 테이블만"""
    table_name = info['table']
    row_count = info.get('row_count', 0)
    korean_count = info.get('korean_count', 0)
    email_count = info.get('email_count', 0)
    
    # 한글/이메일 데이터 표시
    if is_korean:
        marker = "🇰🇷 "
        info_text = f" (한글 {korean_count}자)" if korean_count > 0 else ""
    elif is_email:
        marker = "📧 "
        info_text = f" (이메일 {email_count}개)" if email_count > 0 else ""
    else:
        marker = ""
        info_text = ""
    
    f.write(f"##### {marker}테이블: `{table_name}` ({row_count}행{info_text})\n\n")
    
    if not info["columns"]:
        f.write("_컬럼 정보 없음 또는 오류 발생_\n\n")
        if info["rows"]:
            for row in info["rows"]:
                f.write(f"**오류**: {row}\n\n")
        return
    
    # 데이터가 있는 경우에만 테이블 표시
    if info["rows"] and len(info["rows"]) > 0:
        # 테이블 헤더
        f.write("| " + " | ".join(info["columns"]) + " |\n")
        f.write("| " + " | ".join(["---"] * len(info["columns"])) + " |\n")
        
        # 데이터 행들
        for row in info["rows"]:
            row_str = []
            for col in row:
                if col is None:
                    row_str.append("NULL")
                else:
                    # 마크다운 특수문자 이스케이프 및 길이 제한
                    col_str = str(col).replace("|", "\\|").replace("\n", " ").replace("\r", "")
                    if len(col_str) > 50:
                        col_str = col_str[:47] + "..."
                    row_str.append(col_str)
            f.write("| " + " | ".join(row_str) + " |\n")
    else:
        # 데이터가 없는 경우 간단한 메시지만
        f.write("_데이터 없음 (테이블 스키마만 존재)_\n")
    
    f.write("\n")

def main():
    home = os.path.expanduser("~")
    default_img = os.path.join(home, "Desktop", "fbe-decrypt", "userdata-decrypted.img")
    img_file = input(f"복호화 이미지 경로를 입력해주세요 [{default_img}]: ").strip()
    if not img_file:
        img_file = default_img
    if not os.path.isfile(img_file):
        print(f"[에러] 이미지 파일이 존재하지 않습니다: {img_file}")
        sys.exit(1)
    
    mount_point = os.path.join(home, "mnt")
    output_md = os.path.join(home, "wearos_thirdparty_artifact_report.md")
    
    print(f"[INFO] 분석 대상 이미지 파일: {img_file}")
    print(f"[INFO] 임시 마운트 경로: {mount_point}")
    print(f"[INFO] 결과 보고서: {output_md}")
    
    # 임시 디렉토리 생성 (DB 파일 복사용)
    temp_dir = tempfile.mkdtemp(prefix="wearos_db_")
    print(f"[INFO] 임시 작업 디렉토리: {temp_dir}")
    
    try:
        mount_img(img_file, mount_point)
    except Exception as e:
        print("[오류] 마운트 완전히 실패! 위 출력과 dmesg 참고, loop device 해제(`sudo losetup -D`)도 시도.")
        print(str(e))
        return
    
    try:
        db_files = find_database_files(mount_point)
        print(f"\n[+] 발견된 DB 파일 수: {len(db_files)}")
        
        if not db_files:
            print("[경고] DB 파일이 탐지되지 않았습니다.")
            
            # 추가 디버깅 정보 제공
            print("\n[디버깅] 추가 검사 수행...")
            root_data = os.path.join(mount_point, "data")
            
            # /data 폴더 구조 확인
            try:
                ls_result = subprocess.run(
                    ["sudo", "ls", "-la", root_data],
                    capture_output=True, text=True, timeout=30
                )
                if ls_result.returncode == 0:
                    print(f"[디버깅] /data 폴더 내용:")
                    lines = ls_result.stdout.strip().split('\n')[:20]  # 처음 20줄만
                    for line in lines:
                        print(f"  {line}")
                    if len(ls_result.stdout.strip().split('\n')) > 20:
                        print("  ... (더 많은 폴더 있음)")
            except Exception as e:
                print(f"[디버깅] /data 폴더 확인 실패: {e}")
            
            # 특정 앱 폴더 직접 확인
            test_apps = ["jp.naver.line.android", "com.google.android.keep", "com.coffeebeanventures.easyvoicerecorder"]
            for app in test_apps:
                app_path = os.path.join(root_data, app)
                try:
                    ls_app_result = subprocess.run(
                        ["sudo", "ls", "-la", app_path],
                        capture_output=True, text=True, timeout=10
                    )
                    if ls_app_result.returncode == 0:
                        print(f"[디버깅] {app} 폴더 발견:")
                        for line in ls_app_result.stdout.strip().split('\n')[:10]:
                            print(f"  {line}")
                        
                        # databases 폴더 확인
                        db_path = os.path.join(app_path, "databases")
                        ls_db_result = subprocess.run(
                            ["sudo", "ls", "-la", db_path],
                            capture_output=True, text=True, timeout=10
                        )
                        if ls_db_result.returncode == 0:
                            print(f"[디버깅] {app}/databases 폴더 내용:")
                            for line in ls_db_result.stdout.strip().split('\n'):
                                print(f"    {line}")
                except:
                    print(f"[디버깅] {app} 폴더 없음 또는 접근 불가")
            
            return
        
        # DB 분석 (서드파티 앱 위주)
        db_summaries = {}
        
        print(f"\n[+] 서드파티 앱 DB 파일 분석 시작...")
        for i, db in enumerate(db_files, 1):
            rel_path = os.path.relpath(db, os.path.join(mount_point, "data"))
            app_name = rel_path.split('/')[0]
            
            print(f"[{i}/{len(db_files)}] 분석 중: {rel_path}")
            
            db_summaries[db] = analyze_sqlite_db(db, app_name=app_name, temp_dir=temp_dir)
        
        generate_markdown_report(db_summaries, output_md, mount_point)
        print(f"\n[+] 서드파티 앱 중심 분석 및 보고서 완료: {output_md}")
        
    finally:
        umount_img(mount_point)
        shutil.rmtree(mount_point, ignore_errors=True)
        
        # 임시 디렉토리 정리
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"[+] 임시 디렉토리 정리 완료")

if __name__ == "__main__":
    main() 
