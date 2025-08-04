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
                "com.samsung",              # 삼성 앱들
                "com.sec.",                 # 삼성 시스템 앱들
                "android",                  # 시스템 앱들
            ],
            "priority": 4  # 낮은 우선순위
        }
    }

def find_database_files(mount_point):
    """개선된 DB 검색 - 서드파티 앱 우선"""
    db_paths = []
    root_data = os.path.join(mount_point, "data")
    
    if not os.path.exists(root_data):
        print(f"[경고] /data 폴더가 존재하지 않습니다: {root_data}")
        return []
    
    print("[+] 데이터베이스 파일 검색 중...")
    print(f"[+] 검색 경로: {root_data}")
    
    app_categories = get_app_categories()
    
    # 1단계: 실제 존재하는 앱 폴더들 찾기
    print("\n[+] 1단계: 앱 폴더 검색...")
    try:
        # /data 바로 아래의 모든 폴더 검색
        find_apps_cmd = [
            "sudo", "find", root_data,
            "-maxdepth", "1",
            "-type", "d", 
            "-name", "*.*"   # 패키지명 형태의 폴더들
        ]
        
        result = subprocess.run(find_apps_cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            app_folders = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
            print(f"[+] 발견된 앱 폴더: {len(app_folders)}개")
            
            # 카테고리별로 분류
            categorized_apps = {}
            for category, info in app_categories.items():
                categorized_apps[category] = []
                
            uncategorized = []
            
            for folder in app_folders:
                app_name = os.path.basename(folder)
                categorized = False
                
                for category, info in app_categories.items():
                    if any(app_pattern in app_name for app_pattern in info["apps"]):
                        categorized_apps[category].append((app_name, folder))
                        categorized = True
                        break
                
                if not categorized:
                    uncategorized.append((app_name, folder))
            
            # 카테고리별 출력 (우선순위 순)
            sorted_categories = sorted(app_categories.items(), key=lambda x: x[1]["priority"])
            
            for category, info in sorted_categories:
                if categorized_apps[category]:
                    print(f"\n  📱 {category.upper()} ({len(categorized_apps[category])}개):")
                    for app_name, folder in categorized_apps[category]:
                        print(f"    🔥 {app_name}")
            
            if uncategorized:
                print(f"\n  📱 기타 앱 ({len(uncategorized)}개):")
                for app_name, folder in uncategorized[:10]:
                    print(f"    - {app_name}")
                if len(uncategorized) > 10:
                    print(f"    ... 및 {len(uncategorized)-10}개 더")
                    
        else:
            print("[경고] 앱 폴더 검색 실패")
            
    except Exception as e:
        print(f"[경고] 앱 폴더 검색 오류: {e}")
    
    # 2단계: databases 폴더 검색 및 DB 파일 수집
    print(f"\n[+] 2단계: 서드파티 앱 DB 파일 검색...")
    
    try:
        find_databases_cmd = [
            "sudo", "find", root_data,
            "-type", "d",
            "-name", "databases",
            "-maxdepth", "3"
        ]
        
        result = subprocess.run(find_databases_cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and result.stdout.strip():
            databases_folders = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
            print(f"[+] 발견된 databases 폴더: {len(databases_folders)}개")
            
            # DB 파일 정보를 저장할 리스트
            db_info_list = []
            
            for db_folder in databases_folders:
                if os.path.exists(db_folder):
                    rel_path = os.path.relpath(db_folder, root_data)
                    app_name = rel_path.split('/')[0]
                    
                    try:
                        find_db_cmd = [
                            "sudo", "find", db_folder,
                            "-type", "f",
                            "-name", "*.db",
                            "-size", "+0c"
                        ]
                        
                        db_result = subprocess.run(find_db_cmd, capture_output=True, text=True, timeout=15)
                        
                        if db_result.returncode == 0 and db_result.stdout.strip():
                            found_dbs = [f.strip() for f in db_result.stdout.strip().split('\n') if f.strip()]
                            
                            for db_file in found_dbs:
                                if db_file and os.path.exists(db_file):
                                    # 파일 크기 확인
                                    try:
                                        stat_result = subprocess.run(
                                            ["sudo", "stat", "-c", "%s", db_file],
                                            capture_output=True, text=True
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
                                        "path": db_file,
                                        "app_name": app_name,
                                        "db_name": os.path.basename(db_file),
                                        "size_bytes": size_bytes,
                                        "category": category,
                                        "priority": priority
                                    })
                                    
                    except subprocess.TimeoutExpired:
                        print(f"   ? {app_name}: DB 검색 타임아웃")
                    except Exception as e:
                        print(f"   ? {app_name}: DB 검색 실패 ({e})")
            
            # 우선순위 기준으로 정렬 (서드파티 앱 우선)
            db_info_list.sort(key=lambda x: (x["priority"], -x["size_bytes"]))
            
            # 결과 출력 및 경로 리스트 생성
            print(f"\n[+] DB 파일 분석 우선순위:")
            current_category = None
            
            for db_info in db_info_list:
                if db_info["category"] != current_category:
                    current_category = db_info["category"]
                    print(f"\n  📊 {current_category.upper()}:")
                
                size_kb = db_info["size_bytes"] / 1024
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
            print(f"[경고] databases 폴더를 찾을 수 없습니다")
            
    except Exception as e:
        print(f"[경고] databases 폴더 검색 오류: {e}")
    
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
    """개선된 DB 분석 - 앱별 중요 테이블 우선"""
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
                
                summary.append({
                    "table": table, 
                    "columns": columns, 
                    "rows": rows,
                    "row_count": row_count,
                    "is_important": is_important
                })
                
            except Exception as table_error:
                summary.append({
                    "table": table, 
                    "columns": [], 
                    "rows": [f"테이블 분석 오류: {str(table_error)}"],
                    "row_count": 0,
                    "is_important": False
                })
                
    except Exception as e:
        summary.append({
            "table": "DB_ERROR", 
            "columns": [], 
            "rows": [f"DB 연결 오류: {str(e)}"],
            "row_count": 0,
            "is_important": False
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
    """개선된 마크다운 보고서 생성"""
    app_categories = get_app_categories()
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Wear OS 서드파티 앱 DB 아티팩트 분석 리포트\n\n")
        f.write("이 보고서는 서드파티 앱의 데이터베이스를 우선 분석한 결과입니다.\n\n")
        
        # 요약 섹션
        f.write("## 📊 분석 요약\n\n")
        total_dbs = len(db_summaries)
        
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
        for category, count in sorted(category_stats.items()):
            f.write(f"- **{category.title()}**: {count}개\n")
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
                
                # 우선순위 표시
                priority_marker = {1: "🔥 고우선순위", 2: "⭐ 중우선순위", 3: "📍 저우선순위"}.get(priority, "")
                
                f.write(f"### {priority_marker} `/data/{rel_db_path}`\n\n")
                f.write(f"**앱**: `{app_name}`\n\n")
                
                # 중요한 테이블과 일반 테이블 분리
                important_tables = [t for t in tables if t.get("is_important", False)]
                other_tables = [t for t in tables if not t.get("is_important", False)]
                
                if important_tables:
                    f.write("#### 🔥 주요 데이터 테이블\n\n")
                    for info in important_tables:
                        write_table_info(f, info)
                
                if other_tables:
                    f.write("#### 📋 기타 테이블\n\n")
                    for info in other_tables:
                        write_table_info(f, info)
                
                f.write("---\n\n")

def write_table_info(f, info):
    """테이블 정보를 마크다운으로 작성"""
    table_name = info['table']
    row_count = info.get('row_count', 0)
    
    f.write(f"##### 테이블: `{table_name}` ({row_count}행)\n\n")
    
    if not info["columns"]:
        f.write("_컬럼 정보 없음 또는 오류 발생_\n\n")
        if info["rows"]:
            for row in info["rows"]:
                f.write(f"**오류**: {row}\n\n")
        return
    
    # 데이터가 있는 경우에만 테이블 표시
    if info["rows"]:
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
        f.write("_데이터 없음_\n")
    
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
