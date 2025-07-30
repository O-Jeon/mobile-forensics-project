import subprocess
import os
import glob
import sqlite3

# 1. FBE 복호화 (Node.js 코드 연동)
def decrypt_userdata(encrypted_img, decrypted_img):
    result = subprocess.run([
        'node', 'fbe-decrypt.mjs', encrypted_img, decrypted_img
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"복호화 실패: {result.stderr}")

# 2. img mount 또는 파싱
def mount_or_parse_img(img_path, mount_point):
    # loop device mount 혹은 pytsk3 등 파이썬 모듈 이용 방법 중 선택
    os.makedirs(mount_point, exist_ok=True)
    subprocess.run(['sudo', 'mount', '-o', 'loop,ro', img_path, mount_point], check=True)

# 3. 서드파티 앱 DB 자동 검색
def find_databases(mount_point):
    db_files = glob.glob(os.path.join(mount_point, "data", "data", "*", "databases", "*.db"))
    return db_files

# 4. DB 의미 정보 추출 (example: 모든 테이블 dump)
def analyze_sqlite_db(db_path):
    result = {}
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cur.fetchall()]
    for table in tables:
        cur.execute(f"SELECT * FROM {table} LIMIT 20")  # 샘플만
        rows = cur.fetchall()
        desc = [d[0] for d in cur.description]
        result[table] = {"columns": desc, "rows": rows}
    conn.close()
    return result

# 5. 자동 보고서 작성
def generate_report(db_analysis_results, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        for dbfile, dbresults in db_analysis_results.items():
            f.write(f"## Database: {dbfile}\n")
            for tablename, content in dbresults.items():
                f.write(f"### Table: {tablename}\n")
                f.write(f"Columns: {content['columns']}\n")
                f.write(f"Sample Rows:\n")
                for row in content['rows']:
                    f.write(str(row) + "\n")
                f.write("\n")

def main():
    encrypted_img = 'userdata.img'
    decrypted_img = 'userdata-decrypted.img'
    mount_point = '/mnt/wearos_data'
    output_report = 'wearos_report.md'

    # 1. 복호화
    decrypt_userdata(encrypted_img, decrypted_img)
    # 2. 마운트
    mount_or_parse_img(decrypted_img, mount_point)
    # 3. DB 탐색
    db_files = find_databases(mount_point)
    # 4. 각 DB 분석
    db_analysis_results = {}
    for db in db_files:
        try:
            db_analysis_results[db] = analyze_sqlite_db(db)
        except Exception as e:
            db_analysis_results[db] = {'error': str(e)}
    # 5. 보고서 생성
    generate_report(db_analysis_results, output_report)
    print("완료!")

if __name__ == '__main__':
    main()
