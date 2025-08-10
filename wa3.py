import os
import glob
import sqlite3
import subprocess
import shutil
import sys
import tempfile
import re

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

def has_korean_text(text):
    """텍스트에 한글이 포함되어 있는지 확인"""
    if not text:
        return False
    korean_pattern = re.compile(r'[가-힣]')
    return bool(korean_pattern.search(str(text)))

def has_email_pattern(text):
    """텍스트에 이메일 패턴이 있는지 확인"""
    if not text:
        return False
    email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    return bool(email_pattern.search(str(text)))

def count_korean_chars(text):
    """텍스트의 한글 문자 수를 세기"""
    if not text:
        return 0
    korean_pattern = re.compile(r'[가-힣]')
    return len(korean_pattern.findall(str(text)))

def extract_emails(text):
    """텍스트에서 이메일 주소 추출"""
    if not text:
        return []
    email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    return email_pattern.findall(str(text))

def analyze_table_content(table_info):
    """테이블 내용을 분석하여 한글/이메일 정보 추가"""
    korean_count = 0
    email_count = 0
    has_korean = False
    has_email = False
    
    if table_info.get("rows"):
        for row in table_info["rows"]:
            for cell in row:
                cell_str = str(cell) if cell is not None else ""
                if has_korean_text(cell_str):
                    has_korean = True
                    korean_count += count_korean_chars(cell_str)
                if has_email_pattern(cell_str):
                    has_email = True
                    email_count += len(extract_emails(cell_str))
    
    table_info["has_korean"] = has_korean
    table_info["has_email"] = has_email
    table_info["korean_count"] = korean_count
    table_info["email_count"] = email_count
    
    return table_info

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
    """개선된 DB 분석 - 앱별 중요 테이블 우선, 한글/이메일 데이터 분석"""
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
                
                # 중요한 테이블인지 표시
                is_important = False
                if important_patterns:
                    is_important = any(pattern.lower() in table.lower() for pattern in important_patterns)
                
                table_info = {
                    "table": table, 
                    "columns": columns, 
                    "rows": rows,
                    "row_count": row_count,
                    "is_important": is_important
                }
                
                # 한글/이메일 데이터 분석 추가
                table_info = analyze_table_content(table_info)
                summary.append(table_info)
                
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
                    "email_count": 0
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
            "email_count": 0
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

def generate_html_report(db_summaries, output_path, mount_point):
    """HTML GUI 증거 카드형 보고서 생성"""
    app_categories = get_app_categories()
    
    # 전체 통계 계산
    total_dbs = len(db_summaries)
    total_tables = 0
    tables_with_data = 0
    total_rows = 0
    korean_tables = 0
    email_tables = 0
    total_korean_chars = 0
    total_emails = 0
    
    # 주요 계정 정보 추출
    main_account = None
    
    # 증거 데이터 수집
    evidence_items = []
    evidence_counter = 1
    
    for db_file, tables in db_summaries.items():
        rel_path = os.path.relpath(db_file, os.path.join(mount_point, "data"))
        app_name = rel_path.split('/')[0]
        
        # 카테고리 확인
        category = "기타"
        priority = 5
        for cat, info in app_categories.items():
            if any(app_pattern in app_name for app_pattern in info["apps"]):
                category = cat
                priority = info["priority"]
                break
        
        # 의미 있는 데이터가 있는 테이블들만 수집
        important_data = []
        other_data = []
        
        for table_info in tables:
            if table_info.get('table') in ['DB_ERROR', 'COPY_ERROR']:
                continue
            
            total_tables += 1
            row_count = table_info.get('row_count', 0)
            
            if row_count > 0:
                tables_with_data += 1
                total_rows += row_count
                
                # 한글/이메일 데이터 통계
                if table_info.get('has_korean'):
                    korean_tables += 1
                    total_korean_chars += table_info.get('korean_count', 0)
                
                if table_info.get('has_email'):
                    email_tables += 1
                    total_emails += table_info.get('email_count', 0)
                
                # 주요 계정 정보 추출 (이메일 패턴)
                if not main_account and table_info.get('has_email'):
                    for row in table_info.get('rows', []):
                        for cell in row:
                            cell_str = str(cell) if cell is not None else ""
                            emails = extract_emails(cell_str)
                            if emails and not any(x in emails[0] for x in ['noreply', 'no-reply', 'support']):
                                main_account = emails[0]
                                break
                        if main_account:
                            break
                
                # 중요도에 따라 분류
                if table_info.get("is_important", False) or table_info.get('has_korean') or table_info.get('has_email'):
                    important_data.append(table_info)
                else:
                    other_data.append(table_info)
        
        # 증거로 등록할 만한 데이터가 있으면 추가
        if important_data or (priority <= 2 and other_data):
            # 실제 의미있는 데이터가 있는지 확인
            has_meaningful_data = False
            
            # 한글 또는 이메일 데이터가 있는지 확인
            korean_data = [t for t in important_data + other_data if t.get('has_korean')]
            email_data = [t for t in important_data + other_data if t.get('has_email')]
            
            # 한글/이메일 데이터가 있거나, 높은 우선순위 앱에서 상당한 데이터가 있는 경우만 포함
            if korean_data or email_data:
                has_meaningful_data = True
            elif priority <= 2 and sum(t.get('row_count', 0) for t in important_data + other_data) >= 50:
                has_meaningful_data = True
            
            if has_meaningful_data:
                evidence_items.append({
                    "id": evidence_counter,
                    "app_name": app_name,
                    "db_path": rel_path,
                    "category": category,
                    "priority": priority,
                    "important_tables": important_data,
                    "other_tables": other_data,
                    "total_rows": sum(t.get('row_count', 0) for t in important_data + other_data),
                    "korean_data": korean_data,
                    "email_data": email_data
                })
                evidence_counter += 1
    
    # 우선순위로 정렬
    evidence_items.sort(key=lambda x: (x["priority"], -x["total_rows"]))
    
    # HTML 생성
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wear OS 디지털 증거</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', sans-serif; 
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .evidence-container {{ 
            max-width: 1200px; 
            margin: 0 auto; 
        }}
        .header {{ 
            text-align: center; 
            margin-bottom: 40px;
            color: white;
        }}
        .case-info {{
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.1);
            padding: 25px;
            border-radius: 20px;
            margin-bottom: 30px;
            color: white;
        }}
        .case-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 15px;
        }}
        .case-item {{
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }}
        .evidence-grid {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); 
            gap: 25px; 
        }}
        .evidence-card {{
            background: white;
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            border-top: 5px solid;
        }}
        .evidence-card:hover {{
            transform: translateY(-8px);
            box-shadow: 0 25px 50px rgba(0,0,0,0.3);
        }}
        .evidence-card.critical {{ border-top-color: #dc2626; }}
        .evidence-card.important {{ border-top-color: #ea580c; }}
        .evidence-card.useful {{ border-top-color: #0891b2; }}
        .card-header {{
            padding: 20px;
            background: linear-gradient(135deg, #f8fafc, #e2e8f0);
            border-bottom: 1px solid #e5e7eb;
        }}
        .evidence-id {{
            font-size: 0.9em;
            color: #6b7280;
            margin-bottom: 5px;
        }}
        .evidence-title {{
            font-size: 1.1em;
            font-weight: bold;
            color: #1f2937;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
            line-height: 1.3;
        }}
        .evidence-meta {{
            font-size: 0.9em;
            color: #6b7280;
        }}
        .card-content {{
            padding: 20px;
        }}
        .data-item {{
            background: #f8fafc;
            padding: 10px;
            margin: 6px 0;
            border-radius: 6px;
            border-left: 3px solid #e5e7eb;
            font-size: 0.9em;
            line-height: 1.4;
        }}
        .korean-data {{
            background: linear-gradient(135deg, #fef3c7, #fde68a);
            border-left-color: #f59e0b;
            font-weight: 500;
        }}
        .email-data {{
            background: linear-gradient(135deg, #dbeafe, #bfdbfe);
            border-left-color: #3b82f6;
        }}
        .priority-badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 0.75em;
            font-weight: bold;
            color: white;
            white-space: nowrap;
        }}
        .priority-critical {{ background: #dc2626; }}
        .priority-important {{ background: #ea580c; }}
        .priority-useful {{ background: #0891b2; }}
        .timestamp {{
            font-size: 0.8em;
            color: #9ca3af;
            margin-top: 5px;
        }}
        .data-count {{
            background: #1f2937;
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            margin-left: auto;
        }}
        .evidence-summary {{
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 30px;
            color: white;
            text-align: center;
        }}
        .forensic-note {{
            margin-top: 15px;
            padding: 10px;
            border-radius: 8px;
            font-size: 0.9em;
        }}
        .forensic-critical {{ background: #fef2f2; }}
        .forensic-important {{ background: #fef7ed; }}
        .forensic-useful {{ background: #eff6ff; }}
    </style>
</head>
<body>
    <div class="evidence-container">
        <div class="header">
            <h1>🔍 디지털 포렌식 증거 분석</h1>
            <h2>Wear OS 스마트워치</h2>
        </div>
        
        <div class="case-info">
            <h3>📋 사건 개요</h3>
            <div class="case-grid">
                <div class="case-item">
                    <strong>피의자 계정</strong><br>
                    {main_account or "계정 미확인"}
                </div>
                <div class="case-item">
                    <strong>분석 DB 수</strong><br>
                    {total_dbs}개
                </div>
                <div class="case-item">
                    <strong>주요 증거</strong><br>
                    {len(evidence_items)}개 아이템
                </div>
                <div class="case-item">
                    <strong>한글 데이터</strong><br>
                    {total_korean_chars}자
                </div>
            </div>
        </div>
        
        <div class="evidence-summary">
            <h3>🎯 핵심 증거 요약</h3>
            <p>총 {len(evidence_items)}개의 주요 증거가 발견되었으며, 한국어 텍스트 {korean_tables}개 테이블과 이메일 관련 {email_tables}개 테이블에서 포렌식적 가치가 확인됨</p>
        </div>
        
        <div class="evidence-grid">"""

    # 각 증거 카드 생성
    for item in evidence_items:
        priority_class = "critical" if item["priority"] == 1 else "important" if item["priority"] == 2 else "useful"
        priority_text = "핵심증거" if item["priority"] == 1 else "중요증거" if item["priority"] == 2 else "참고증거"
        
        # 앱 이름에 따른 아이콘
        app_icon = "💬" if "messaging" in item["category"] else "📝" if "productivity" in item["category"] else "📧" if "email" in item["category"] else "📱"
        
        html_content += f"""
            <div class="evidence-card {priority_class}">
                <div class="card-header">
                    <div class="evidence-id">Evidence #{item["id"]:03d}</div>
                    <div class="evidence-title">
                        {app_icon} {item["app_name"]}
                        <span class="priority-badge priority-{priority_class}">{priority_text}</span>
                    </div>
                    <div class="evidence-meta">
                        위치: /data/{item["db_path"]}
                    </div>
                </div>
                <div class="card-content">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <strong>발견된 데이터</strong>
                        <span class="data-count">{item["total_rows"]}건</span>
                    </div>"""
        
        # 한글 데이터가 있는 경우
        if item["korean_data"]:
            html_content += """
                    <div style="margin-bottom: 15px;">
                        <strong>🇰🇷 한글 데이터</strong>
                    </div>"""
            
            for table in item["korean_data"][:3]:  # 최대 3개 테이블만 표시
                html_content += f"""
                    <div class="data-item korean-data">
                        <strong>{table["table"]}</strong> ({table["row_count"]}행)"""
                
                # 한글 텍스트 샘플 표시
                korean_samples = []
                for row in table.get("rows", [])[:3]:  # 최대 3개 행만
                    for cell in row:
                        cell_str = str(cell) if cell is not None else ""
                        if has_korean_text(cell_str):
                            text = cell_str[:100]  # 100자 제한
                            if text and text not in korean_samples:
                                korean_samples.append(f'"{text}"')
                
                if korean_samples:
                    # 텍스트가 너무 길면 줄바꿈 방지를 위해 더 짧게 자르기
                    short_samples = []
                    for sample in korean_samples[:3]:
                        if len(sample) > 50:
                            short_samples.append(sample[:47] + '..."')
                        else:
                            short_samples.append(sample)
                    
                    html_content += f"""
                        <div style="margin-top: 6px; font-size: 0.85em; line-height: 1.3; word-break: break-all;">
                            {', '.join(short_samples)}
                        </div>"""
                
                html_content += """
                    </div>"""
        
        # 이메일 데이터가 있는 경우
        if item["email_data"]:
            html_content += """
                    <div style="margin-bottom: 15px;">
                        <strong>📧 이메일 관련 데이터</strong>
                    </div>"""
            
            for table in item["email_data"][:2]:  # 최대 2개 테이블만 표시
                html_content += f"""
                    <div class="data-item email-data">
                        <strong>{table["table"]}</strong> ({table["row_count"]}행)"""
                
                # 이메일 주소 샘플 표시
                email_samples = []
                for row in table.get("rows", [])[:5]:  # 최대 5개 행만
                    for cell in row:
                        cell_str = str(cell) if cell is not None else ""
                        emails = extract_emails(cell_str)
                        for email in emails:
                            if email and email not in email_samples:
                                email_samples.append(email)
                
                if email_samples:
                    html_content += f"""
                        <div style="margin-top: 8px; font-size: 0.9em;">
                            {', '.join(email_samples[:5])}
                        </div>"""
                
                html_content += """
                    </div>"""
        
        # 기타 중요 데이터
        if item["important_tables"] and not item["korean_data"] and not item["email_data"]:
            html_content += """
                    <div style="margin-bottom: 15px;">
                        <strong>📊 주요 테이블</strong>
                    </div>"""
            
            for table in item["important_tables"][:3]:
                html_content += f"""
                    <div class="data-item">
                        <strong>{table["table"]}</strong> ({table["row_count"]}행)
                    </div>"""
        
        # 포렌식 의미 설명
        forensic_class = f"forensic-{priority_class}"
        forensic_meaning = ""
        
        if item["korean_data"]:
            forensic_meaning = "사용자의 한국어 텍스트 입력 패턴 및 개인 정보 확인 가능"
        elif item["email_data"]:
            forensic_meaning = "계정 연동 정보 및 외부 서비스 이용 현황 파악 가능"
        elif "messaging" in item["category"]:
            forensic_meaning = "메시징 활동 및 커뮤니케이션 패턴 분석 가능"
        elif "productivity" in item["category"]:
            forensic_meaning = "개인 메모 및 업무 관련 활동 내역 확인 가능"
        else:
            forensic_meaning = "시스템 사용 패턴 및 앱 활동 로그 분석 가능"
        
        html_content += f"""
                    <div class="{forensic_class} forensic-note">
                        📍 <strong>포렌식 의미:</strong> {forensic_meaning}
                    </div>
                </div>
            </div>"""
    
    # HTML 마무리
    html_content += f"""
        </div>
        
        <div style="background: rgba(255,255,255,0.05); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.1); padding: 25px; border-radius: 20px; margin-top: 30px; color: white; text-align: center;">
            <h3>📊 증거 분석 결론</h3>
            <div style="margin-top: 15px; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                <div>
                    <div style="font-size: 2em; font-weight: bold; color: #fbbf24;">{len(evidence_items)}</div>
                    <div>주요 증거 그룹</div>
                </div>
                <div>
                    <div style="font-size: 2em; font-weight: bold; color: #fbbf24;">{total_rows:,}</div>
                    <div>총 데이터 건수</div>
                </div>
                <div>
                    <div style="font-size: 2em; font-weight: bold; color: #fbbf24;">{total_korean_chars}</div>
                    <div>한글 문자 수</div>
                </div>
                <div>
                    <div style="font-size: 2em; font-weight: bold; color: #fbbf24;">{total_emails}</div>
                    <div>이메일 주소 수</div>
                </div>
            </div>
            <div style="margin-top: 20px; padding: 15px; background: rgba(59, 130, 246, 0.2); border-radius: 10px;">
                <strong>권고사항:</strong> 휴대폰 본체 및 클라우드 동기화 데이터 추가 분석 필요
            </div>
        </div>
    </div>
</body>
</html>"""
    
    # HTML 파일 저장
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

def generate_markdown_report(db_summaries, output_path, mount_point):
    """간소화된 백업용 마크다운 보고서 생성"""
    app_categories = get_app_categories()
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Wear OS 서드파티 앱 DB 분석 백업 리포트\n\n")
        f.write("이 파일은 HTML 보고서의 백업용 마크다운 버전입니다.\n\n")
        
        # 간단한 통계만 포함
        total_dbs = len(db_summaries)
        total_tables = 0
        tables_with_data = 0
        
        for db_file, tables in db_summaries.items():
            for table_info in tables:
                if table_info.get('table') not in ['DB_ERROR', 'COPY_ERROR']:
                    total_tables += 1
                    if table_info.get('row_count', 0) > 0:
                        tables_with_data += 1
        
        f.write(f"## 📊 요약\n\n")
        f.write(f"- 총 DB 파일: {total_dbs}개\n")
        f.write(f"- 총 테이블: {total_tables}개\n") 
        f.write(f"- 데이터 보유 테이블: {tables_with_data}개\n\n")
        f.write(f"상세 분석 결과는 HTML 보고서를 참조하세요.\n")

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
    output_html = os.path.join(home, "wearos_forensic_evidence_report.html")
    output_md = os.path.join(home, "wearos_thirdparty_artifact_report_backup.md")
    
    print(f"[INFO] 분석 대상 이미지 파일: {img_file}")
    print(f"[INFO] 임시 마운트 경로: {mount_point}")
    print(f"[INFO] HTML 보고서: {output_html}")
    print(f"[INFO] 백업 마크다운: {output_md}")
    
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
        
        # HTML 증거 카드형 보고서 생성
        generate_html_report(db_summaries, output_html, mount_point)
        print(f"\n[+] 🎯 HTML 포렌식 증거 보고서 완료: {output_html}")
        
        # 백업용 마크다운도 생성 (간소화)
        try:
            generate_markdown_report(db_summaries, output_md, mount_point)
            print(f"[+] 📄 백업 마크다운 보고서 완료: {output_md}")
        except Exception as e:
            print(f"[경고] 백업 마크다운 생성 실패: {e}")
        
        print(f"\n🔍 주요 결과:")
        print(f"  - HTML 보고서를 브라우저에서 열어 시각적 분석 결과를 확인하세요")
        print(f"  - 증거 카드 형식으로 포렌식 분석 결과가 정리되었습니다")
        
    finally:
        umount_img(mount_point)
        shutil.rmtree(mount_point, ignore_errors=True)
        
        # 임시 디렉토리 정리
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"[+] 임시 디렉토리 정리 완료")

if __name__ == "__main__":
    main()