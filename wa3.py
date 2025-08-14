#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
통합 Android FBE 복호화 및 WearOS 포렌식 분석 도구
FBE 복호화 후 자동으로 데이터베이스 아티팩트를 분석하고 포렌식 보고서를 생성합니다.
"""

import subprocess
import sys
import os
import hashlib
import time
import platform
import getpass
import json
import glob
import sqlite3
import shutil
import tempfile
import statistics
import re
import logging
from datetime import datetime, timezone
from pathlib import Path

# Check for required packages
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class IntegratedDecryptionAndForensicsLogger:
    def __init__(self):
        self.start_time = datetime.now(timezone.utc)
        self.log_file = f"integrated_analysis_log_{self.start_time.strftime('%Y%m%d_%H%M%S')}.log"
        self.metadata = {}
        self.temp_dir = None
        
    def log_and_print(self, message, file_only=False):
        """콘솔과 로그 파일에 동시 출력"""
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        log_message = f"[{timestamp}] {message}"
        
        if not file_only:
            print(message)
            sys.stdout.flush()  # 즉시 출력
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_message + '\n')
        except Exception as e:
            print(f"로그 파일 쓰기 실패: {e}")
    
    def collect_system_info(self):
        """시스템 정보 수집 (타임아웃 추가)"""
        print("DEBUG: collect_system_info 시작")
        self.log_and_print("시스템 정보 수집 중...")
        
        # 기본 정보
        print("DEBUG: 기본 정보 수집...")
        try:
            self.metadata.update({
                'worker': getpass.getuser(),
                'start_time': self.start_time.isoformat(),
                'timezone_info': {
                    'utc': self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC'),
                    'local': self.start_time.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z'),
                    'timezone': str(self.start_time.astimezone().tzinfo)
                }
            })
            print("DEBUG: 기본 정보 완료")
        except Exception as e:
            print(f"DEBUG: 기본 정보 실패: {e}")
        
        # OS 정보
        print("DEBUG: OS 정보 수집...")
        try:
            os_info = {
                'name': platform.system(),
                'version': platform.version(),
                'release': platform.release(),
                'architecture': platform.architecture()[0],
                'machine': platform.machine(),
                'platform': platform.platform()
            }
            self.metadata['os_info'] = os_info
            self.log_and_print(f"OS: {os_info['name']} {os_info['release']} ({os_info['architecture']})")
            print("DEBUG: OS 정보 완료")
            
        except Exception as e:
            print(f"DEBUG: OS 정보 실패: {e}")
            self.log_and_print(f"OS 정보 수집 실패: {e}")
        
        # Python 버전
        print("DEBUG: Python 정보 수집...")
        try:
            python_version = {
                'version': platform.python_version(),
                'implementation': platform.python_implementation(),
                'compiler': platform.python_compiler()
            }
            self.metadata['python_info'] = python_version
            self.log_and_print(f"Python: {python_version['version']} ({python_version['implementation']})")
            print("DEBUG: Python 정보 완료")
            
        except Exception as e:
            print(f"DEBUG: Python 정보 실패: {e}")
            self.log_and_print(f"Python 정보 수집 실패: {e}")
        
        # Node.js 버전 (타임아웃 추가)
        print("DEBUG: Node.js 정보 수집...")
        try:
            result = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True, timeout=5)
            nodejs_version = result.stdout.strip()
            self.metadata['nodejs_version'] = nodejs_version
            self.log_and_print(f"Node.js: {nodejs_version}")
            print("DEBUG: Node.js 정보 완료")
            
        except subprocess.TimeoutExpired:
            print("DEBUG: Node.js 타임아웃")
            self.log_and_print("Node.js 명령 타임아웃")
            self.metadata['nodejs_version'] = 'timeout'
        except Exception as e:
            print(f"DEBUG: Node.js 정보 실패: {e}")
            self.log_and_print(f"Node.js 정보 수집 실패: {e}")
            self.metadata['nodejs_version'] = f'error: {e}'
        
        # CPU/메모리 정보
        print("DEBUG: 하드웨어 정보 수집...")
        if PSUTIL_AVAILABLE:
            try:
                cpu_info = {
                    'cpu_count': psutil.cpu_count(),
                    'cpu_count_logical': psutil.cpu_count(logical=True),
                    'cpu_freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
                }
                
                memory_info = psutil.virtual_memory()._asdict()
                
                self.metadata['hardware_info'] = {
                    'cpu': cpu_info,
                    'memory': memory_info
                }
                
                self.log_and_print(f"CPU: {cpu_info['cpu_count_logical']}코어")
                self.log_and_print(f"메모리: {memory_info['total'] / (1024**3):.1f} GB")
                print("DEBUG: 하드웨어 정보 완료")
                
            except Exception as e:
                print(f"DEBUG: 하드웨어 정보 실패: {e}")
                self.log_and_print(f"하드웨어 정보 수집 실패: {e}")
        else:
            print("DEBUG: psutil 사용 불가")
            self.log_and_print("psutil 사용 불가 - 하드웨어 정보 건너뛰기")
        
        # Git 정보 (타임아웃 추가)
        print("DEBUG: Git 정보 수집...")
        try:
            if os.path.exists('.git'):
                print("DEBUG: .git 디렉토리 발견")
                
                # Git hash 가져오기
                result = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                                      capture_output=True, text=True, check=True, timeout=5)
                git_hash = result.stdout.strip()
                print(f"DEBUG: Git hash: {git_hash[:8]}")
                
                # Git describe 가져오기  
                result = subprocess.run(['git', 'describe', '--always', '--dirty'], 
                                      capture_output=True, text=True, check=True, timeout=5)
                git_describe = result.stdout.strip()
                print(f"DEBUG: Git describe: {git_describe}")
                
                self.metadata['git_info'] = {
                    'commit_hash': git_hash,
                    'describe': git_describe
                }
                self.log_and_print(f"Git commit: {git_hash[:8]} ({git_describe})")
                print("DEBUG: Git 정보 완료")
            else:
                print("DEBUG: .git 디렉토리 없음")
                self.metadata['git_info'] = {'status': 'no_git_directory'}
                self.log_and_print("Git 정보 없음 (Git 저장소가 아님)")
                
        except subprocess.TimeoutExpired:
            print("DEBUG: Git 명령 타임아웃")
            self.log_and_print("Git 명령 타임아웃")
            self.metadata['git_info'] = {'status': 'timeout'}
        except Exception as e:
            print(f"DEBUG: Git 정보 실패: {e}")
            self.log_and_print(f"Git 정보 수집 실패: {e}")
            self.metadata['git_info'] = {'status': 'error', 'error': str(e)}
        
        print("DEBUG: collect_system_info 완료")
    
    def calculate_file_hash(self, file_path):
        """파일 해시 계산 (진행률 표시)"""
        if not os.path.exists(file_path):
            return None
            
        self.log_and_print(f"파일 해시 계산 중: {file_path}")
        file_size = os.path.getsize(file_path)
        self.log_and_print(f"파일 크기: {file_size / (1024**3):.2f} GB")
        
        sha256_hash = hashlib.sha256()
        processed_bytes = 0
        start_time = time.time()
        
        with open(file_path, "rb") as f:
            while True:
                byte_block = f.read(4096)
                if not byte_block:
                    break
                sha256_hash.update(byte_block)
                processed_bytes += len(byte_block)
                
                # 진행률 출력 (1GB마다)
                if processed_bytes % (1024**3) == 0 or processed_bytes == file_size:
                    progress = (processed_bytes / file_size) * 100
                    elapsed = time.time() - start_time
                    progress_msg = f"진행률: {progress:.1f}% ({processed_bytes / (1024**3):.2f} GB / {file_size / (1024**3):.2f} GB) - 경과시간: {elapsed:.1f}초"
                    self.log_and_print(progress_msg)
        
        return sha256_hash.hexdigest()
    
    def collect_file_metadata(self, file_path):
        """파일 메타데이터 수집"""
        if not os.path.exists(file_path):
            return None
        
        try:
            stat = os.stat(file_path)
            metadata = {
                'path': os.path.abspath(file_path),
                'size': stat.st_size,
                'size_gb': stat.st_size / (1024**3),
                'modified_time': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                'created_time': datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat(),
                'permissions': oct(stat.st_mode)[-3:],
                'hash_sha256': self.calculate_file_hash(file_path)
            }
            return metadata
        except Exception as e:
            self.log_and_print(f"파일 메타데이터 수집 실패 ({file_path}): {e}")
            return None
    
    def check_prerequisites(self):
        """필요한 파일들이 존재하는지 확인"""
        print("DEBUG: check_prerequisites 시작")
        self.log_and_print("사전 요구사항 확인 중...")
        
        required_files = [
            'fbe-decrypt.mjs',
            'encryptionkey.img.qcow2',
            'userdata-qemu.img.qcow2'
        ]
        
        missing_files = []
        file_metadata = {}
        
        for file in required_files:
            print(f"DEBUG: 파일 확인 중: {file}")
            if not os.path.exists(file):
                missing_files.append(file)
                print(f"DEBUG: 파일 누락: {file}")
            else:
                self.log_and_print(f"파일 확인: {file}")
                print(f"DEBUG: 파일 존재: {file}")
                # 해시 계산은 시간이 오래 걸리므로 나중에 하거나 건너뛰기
                try:
                    stat = os.stat(file)
                    file_metadata[file] = {
                        'path': os.path.abspath(file),
                        'size': stat.st_size,
                        'size_gb': stat.st_size / (1024**3)
                    }
                except Exception as e:
                    print(f"DEBUG: 파일 정보 수집 실패 {file}: {e}")
        
        self.metadata['input_files'] = file_metadata
        
        if missing_files:
            self.log_and_print("다음 필수 파일들이 누락되었습니다:")
            for file in missing_files:
                self.log_and_print(f"  - {file}")
            print("DEBUG: 필수 파일 누락")
            return False
        
        # Node.js 설치 확인 (타임아웃 추가)
        print("DEBUG: Node.js 실행 가능성 확인...")
        try:
            result = subprocess.run(['node', '--version'], capture_output=True, check=True, timeout=5)
            print("DEBUG: Node.js 실행 가능")
        except subprocess.TimeoutExpired:
            print("DEBUG: Node.js 타임아웃")
            self.log_and_print("Node.js 명령이 응답하지 않습니다.")
            return False
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("DEBUG: Node.js 설치되지 않음")
            self.log_and_print("Node.js가 설치되어 있지 않습니다.")
            self.log_and_print("Node.js를 설치해주세요: https://nodejs.org/")
            return False
        
        self.log_and_print("모든 필수 파일이 존재합니다.")
        print("DEBUG: check_prerequisites 완료")
        return True
    
    def run_decryption(self):
        """복호화 스크립트 실행"""
        print("DEBUG: run_decryption 시작")
        self.log_and_print("="*60)
        self.log_and_print("Android FBE 복호화를 시작합니다...")
        self.log_and_print("="*60)
        
        decryption_start = datetime.now(timezone.utc)
        
        # 원본 파일 SHA-256 계산 (실제 존재하는 파일 찾기)
        possible_original_files = [
            'userdata-qemu.img.qcow2',
            'userdata(1).img',
            'userdata.img',
            'userdata-qemu.img'
        ]
        
        original_file = None
        original_hash = None
        
        for filename in possible_original_files:
            if os.path.exists(filename):
                original_file = filename
                try:
                    self.log_and_print(f"🔍 원본 파일 무결성 검증 중: {filename}")
                    # 파일 크기 확인 (너무 큰 파일은 경고만)
                    file_size = os.path.getsize(filename)
                    if file_size > 10 * 1024 * 1024 * 1024:  # 10GB 이상
                        self.log_and_print(f"⚠️  파일이 매우 큽니다 ({file_size / (1024**3):.1f}GB). 해시 계산에 시간이 오래 걸릴 수 있습니다.")
                    
                    # 청크 단위로 읽어서 해시 계산 (메모리 효율적)
                    hash_sha256 = hashlib.sha256()
                    with open(original_file, 'rb') as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash_sha256.update(chunk)
                    
                    original_hash = hash_sha256.hexdigest()
                    self.log_and_print(f"✅ 원본 파일 해시: {original_hash}")
                    break
                    
                except PermissionError:
                    self.log_and_print(f"⚠️  파일 읽기 권한이 없습니다: {filename}")
                    continue
                except OSError as e:
                    self.log_and_print(f"⚠️  파일 읽기 오류: {filename} - {e}")
                    continue
                except Exception as e:
                    self.log_and_print(f"⚠️  해시 계산 중 예상치 못한 오류: {filename} - {e}")
                    continue
        
        if not original_file:
            self.log_and_print("⚠️  원본 이미지 파일을 찾을 수 없습니다.")
            self.log_and_print("💡 다음 파일 중 하나가 필요합니다:")
            for filename in possible_original_files:
                self.log_and_print(f"   - {filename}")
            self.log_and_print("💡 또는 현재 디렉토리에 있는 이미지 파일명을 확인하세요.")
            self.log_and_print("💡 해시 계산을 건너뛰고 복호화를 진행합니다.")
        else:
            self.log_and_print(f"✅ 원본 파일 확인됨: {original_file}")
        
        try:
            print("DEBUG: node fbe-decrypt.mjs 실행...")
            result = subprocess.run(
                ['node', 'fbe-decrypt.mjs'],
                capture_output=True,
                text=True,
                check=True,
                timeout=900  # 5분 타임아웃
            )
            
            decryption_end = datetime.now(timezone.utc)
            decryption_duration = (decryption_end - decryption_start).total_seconds()
            
            # 복호화된 파일 SHA-256 계산
            decrypted_file = 'userdata-decrypted.img'
            decrypted_hash = None
            if os.path.exists(decrypted_file):
                try:
                    self.log_and_print("🔍 복호화된 파일 무결성 검증 중...")
                    
                    # 파일 크기 확인
                    file_size = os.path.getsize(decrypted_file)
                    if file_size > 10 * 1024 * 1024 * 1024:  # 10GB 이상
                        self.log_and_print(f"⚠️  복호화된 파일이 매우 큽니다 ({file_size / (1024**3):.1f}GB). 해시 계산에 시간이 오래 걸릴 수 있습니다.")
                    
                    # 청크 단위로 읽어서 해시 계산 (메모리 효율적)
                    hash_sha256 = hashlib.sha256()
                    with open(decrypted_file, 'rb') as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash_sha256.update(chunk)
                    
                    decrypted_hash = hash_sha256.hexdigest()
                    self.log_and_print(f"✅ 복호화된 파일 해시: {decrypted_hash}")
                    
                except PermissionError:
                    self.log_and_print("⚠️  복호화된 파일 읽기 권한이 없습니다.")
                except OSError as e:
                    self.log_and_print(f"⚠️  복호화된 파일 읽기 오류: {e}")
                except Exception as e:
                    self.log_and_print(f"⚠️  복호화된 파일 해시 계산 중 예상치 못한 오류: {e}")
            else:
                self.log_and_print("⚠️  복호화된 파일이 아직 생성되지 않았습니다.")
            
            self.log_and_print("복호화 스크립트 출력:")
            for line in result.stdout.splitlines():
                self.log_and_print(f"  {line}")
            
            if result.stderr:
                self.log_and_print("경고/오류 메시지:")
                for line in result.stderr.splitlines():
                    self.log_and_print(f"  {line}")
            
            self.metadata['decryption_process'] = {
                'start_time': decryption_start.isoformat(),
                'end_time': decryption_end.isoformat(),
                'duration_seconds': decryption_duration,
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'original_file_hash': original_hash,
                'decrypted_file_hash': decrypted_hash
            }
            
            # 복호화 성공 여부 확인
            if os.path.exists(decrypted_file) and os.path.getsize(decrypted_file) > 0:
                self.log_and_print(f"✅ 복호화가 성공적으로 완료되었습니다! (소요시간: {decryption_duration:.1f}초)")
                self.log_and_print(f"📁 생성된 파일: {decrypted_file} ({os.path.getsize(decrypted_file) / (1024**3):.1f}GB)")
                print("DEBUG: run_decryption 성공")
                return True
            else:
                self.log_and_print("❌ 복호화 스크립트는 실행되었으나 결과 파일이 생성되지 않았습니다.")
                self.log_and_print("💡 가능한 원인:")
                self.log_and_print("   - 복호화 키가 올바르지 않음")
                self.log_and_print("   - 원본 파일이 손상됨")
                self.log_and_print("   - 디스크 공간 부족")
                self.log_and_print("   - fbe-decrypt.mjs 스크립트 내부 오류")
                print("DEBUG: run_decryption 실패 - 결과 파일 없음")
                return False
            
        except subprocess.TimeoutExpired:
            print("DEBUG: 복호화 타임아웃")
            self.log_and_print("복호화 스크립트가 타임아웃되었습니다.")
            return False
        except subprocess.CalledProcessError as e:
            print(f"DEBUG: 복호화 실패: {e}")
            self.log_and_print(f"❌ 복호화 스크립트 실행 중 오류 발생:")
            self.log_and_print(f"   리턴 코드: {e.returncode}")
            
            if e.stdout:
                self.log_and_print(f"   표준 출력: {e.stdout}")
            if e.stderr:
                self.log_and_print(f"   오류 출력: {e.stderr}")
            
            # 일반적인 오류 코드별 안내
            if e.returncode == 1:
                self.log_and_print("💡 일반적인 오류 (코드 1):")
                self.log_and_print("   - 복호화 키가 올바르지 않음")
                self.log_and_print("   - 원본 파일 형식이 지원되지 않음")
                self.log_and_print("   - 파일 시스템 오류")
            elif e.returncode == 2:
                self.log_and_print("💡 설정 오류 (코드 2):")
                self.log_and_print("   - 필수 매개변수 누락")
                self.log_and_print("   - 설정 파일 오류")
            elif e.returncode == 127:
                self.log_and_print("💡 명령어를 찾을 수 없음 (코드 127):")
                self.log_and_print("   - Node.js가 설치되지 않음")
                self.log_and_print("   - PATH 설정 문제")
            
            self.metadata['decryption_process'] = {
                'start_time': decryption_start.isoformat(),
                'end_time': datetime.now(timezone.utc).isoformat(),
                'return_code': e.returncode,
                'stdout': e.stdout,
                'stderr': e.stderr,
                'success': False
            }
            return False
        
        except FileNotFoundError:
            print("DEBUG: Node.js 또는 파일 없음")
            self.log_and_print("Node.js가 설치되어 있지 않거나 fbe-decrypt.mjs 파일을 찾을 수 없습니다.")
            return False
    
    # 포렌식 분석 관련 메서드들
    def mount_img(self, img_path, mount_point):
        """이미지 파일 마운트"""
        if not os.path.isfile(img_path):
            raise FileNotFoundError(f"[오류] 이미지 파일이 존재하지 않습니다: {img_path}")
        
        self.log_and_print(f"🔍 이미지 파일 마운트 시도: {img_path}")
        self.log_and_print(f"📍 마운트 포인트: {mount_point}")
        
        # 마운트 포인트 생성
        try:
            os.makedirs(mount_point, exist_ok=True)
            self.log_and_print("✅ 마운트 포인트 생성 완료")
        except Exception as e:
            raise RuntimeError(f"마운트 포인트 생성 실패: {e}")
        
        # 기존 마운트 해제 시도
        try:
            subprocess.run(["sudo", "umount", mount_point], stderr=subprocess.DEVNULL, timeout=10)
            self.log_and_print("✅ 기존 마운트 해제 완료")
        except subprocess.TimeoutExpired:
            self.log_and_print("⚠️  기존 마운트 해제 타임아웃 (무시하고 진행)")
        except Exception as e:
            self.log_and_print(f"⚠️  기존 마운트 해제 실패 (무시하고 진행): {e}")
        
        # 파일시스템 타입 확인
        try:
            file_result = subprocess.run(
                ["file", img_path], 
                capture_output=True, text=True, timeout=10
            )
            if file_result.returncode == 0:
                self.log_and_print(f"📁 파일시스템 정보: {file_result.stdout.strip()}")
        except Exception as e:
            self.log_and_print(f"⚠️  파일시스템 정보 확인 실패: {e}")
        
        # 마운트 시도 (여러 옵션으로)
        mount_options = [
            ["-o", "loop,ro,noload"],
            ["-o", "loop,ro"],
            ["-o", "ro,noload"],
            ["-o", "ro"]
        ]
        
        mount_success = False
        last_error = None
        
        for i, options in enumerate(mount_options, 1):
            self.log_and_print(f"🔄 마운트 시도 {i}/{len(mount_options)}: mount {' '.join(options)} {img_path} {mount_point}")
            
            try:
                result = subprocess.run(
                    ["sudo", "mount"] + options + [img_path, mount_point],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0:
                    self.log_and_print(f"✅ 마운트 성공! 옵션: {' '.join(options)}")
                    mount_success = True
                    break
                else:
                    last_error = result.stderr.strip()
                    self.log_and_print(f"❌ 마운트 실패 {i}: {last_error}")
                    
            except subprocess.TimeoutExpired:
                self.log_and_print(f"⏰ 마운트 시도 {i} 타임아웃")
                last_error = "마운트 명령 타임아웃"
            except Exception as e:
                self.log_and_print(f"❌ 마운트 시도 {i} 예외: {e}")
                last_error = str(e)
        
        if not mount_success:
            self.log_and_print("\n🚨 모든 마운트 시도가 실패했습니다!")
            self.log_and_print("🔧 문제 해결 방법:")
            self.log_and_print("  1. sudo 권한이 올바르게 설정되었는지 확인")
            self.log_and_print("  2. 이미지 파일이 손상되지 않았는지 확인")
            self.log_and_print("  3. 충분한 디스크 공간이 있는지 확인")
            self.log_and_print("  4. dmesg | tail -30 명령으로 커널 에러 확인")
            self.log_and_print("  5. 이미지 파일이 올바른 파일시스템 형식인지 확인")
            
            if last_error:
                self.log_and_print(f"\n📋 마지막 오류 메시지: {last_error}")
            
            raise RuntimeError("모든 마운트 옵션으로 시도했으나 실패했습니다.")
        
        # 마운트 확인
        try:
            mount_check = subprocess.run(
                ["mount"], capture_output=True, text=True, timeout=10
            )
            if mount_check.returncode == 0:
                for line in mount_check.stdout.splitlines():
                    if mount_point in line:
                        self.log_and_print(f"✅ 마운트 상태 확인: {line.strip()}")
                        break
        except Exception as e:
            self.log_and_print(f"⚠️  마운트 상태 확인 실패: {e}")
        
        self.log_and_print(f"🎯 마운트 완료: {mount_point}")
    
    def umount_img(self, mount_point):
        """이미지 파일 언마운트"""
        subprocess.run(["sudo", "umount", mount_point], stderr=subprocess.DEVNULL)
        self.log_and_print(f"[+] 마운트 해제: {mount_point}")
    
    def copy_db_with_sudo(self, src_db_path, temp_dir):
        """sudo로 DB 파일을 임시 디렉토리에 복사하고 읽을 수 있게 권한 변경"""
        try:
            db_name = os.path.basename(src_db_path)
            temp_db_path = os.path.join(temp_dir, db_name)
            
            self.log_and_print(f"    📋 DB 파일 복사 중: {db_name}")
            
            # 파일 크기 확인
            try:
                stat_result = subprocess.run(
                    ["sudo", "stat", "-c", "%s", src_db_path],
                    capture_output=True, text=True, timeout=10
                )
                if stat_result.returncode == 0:
                    size_bytes = int(stat_result.stdout.strip())
                    size_mb = size_bytes / (1024 * 1024)
                    self.log_and_print(f"      📊 파일 크기: {size_mb:.2f} MB")
                    
                    # 파일이 너무 큰 경우 경고
                    if size_mb > 100:  # 100MB 이상
                        self.log_and_print(f"      ⚠️  대용량 파일 (100MB 초과)")
            except Exception as e:
                self.log_and_print(f"      ⚠️  파일 크기 확인 실패: {e}")
            
            # sudo로 파일 복사 (진행률 표시)
            self.log_and_print(f"      🔄 파일 복사 시작...")
            copy_start = time.time()
            
            result = subprocess.run(
                ["sudo", "cp", src_db_path, temp_db_path],
                capture_output=True, text=True, timeout=60  # 1분 타임아웃
            )
            
            if result.returncode != 0:
                self.log_and_print(f"      ❌ 파일 복사 실패: {result.stderr.strip()}")
                return None
            
            copy_time = time.time() - copy_start
            self.log_and_print(f"      ✅ 파일 복사 완료 ({copy_time:.1f}초)")
            
            # 복사된 파일 존재 확인
            if not os.path.exists(temp_db_path):
                self.log_and_print(f"      ❌ 복사된 파일을 찾을 수 없음")
                return None
            
            # 권한 변경으로 읽을 수 있게 만들기
            try:
                chmod_result = subprocess.run(
                    ["sudo", "chmod", "644", temp_db_path],
                    capture_output=True, text=True, timeout=10
                )
                if chmod_result.returncode == 0:
                    self.log_and_print(f"      ✅ 파일 권한 변경 완료 (644)")
                else:
                    self.log_and_print(f"      ⚠️  권한 변경 실패: {chmod_result.stderr.strip()}")
            except Exception as e:
                self.log_and_print(f"      ⚠️  권한 변경 중 오류: {e}")
            
            # 소유권 변경 (현재 사용자로)
            try:
                current_user = os.getenv('USER', getpass.getuser())
                chown_result = subprocess.run(
                    ["sudo", "chown", f"{current_user}:{current_user}", temp_db_path],
                    capture_output=True, text=True, timeout=10
                )
                if chown_result.returncode == 0:
                    self.log_and_print(f"      ✅ 소유권 변경 완료 ({current_user})")
                else:
                    self.log_and_print(f"      ⚠️  소유권 변경 실패: {chown_result.stderr.strip()}")
            except Exception as e:
                self.log_and_print(f"      ⚠️  소유권 변경 중 오류: {e}")
            
            # 최종 확인
            if os.path.exists(temp_db_path):
                final_size = os.path.getsize(temp_db_path)
                self.log_and_print(f"      ✅ 최종 확인: {final_size} bytes")
                return temp_db_path
            else:
                self.log_and_print(f"      ❌ 최종 확인 실패: 파일이 존재하지 않음")
                return None
            
        except subprocess.TimeoutExpired:
            self.log_and_print(f"      ⏰ DB 복사 타임아웃: {src_db_path}")
            return None
        except Exception as e:
            self.log_and_print(f"      ❌ DB 복사 실패 {src_db_path}: {e}")
            return None
    
    def get_app_categories(self):
        """앱을 카테고리별로 분류"""
        return {
            "messaging": {
                "apps": [
                    "com.kakao.talk", "jp.naver.line.android", "com.whatsapp",
                    "com.facebook.orca", "com.discord", "org.telegram.messenger",
                    "com.skype.raider", "com.viber.voip"
                ],
                "priority": 1
            },
            "social": {
                "apps": [
                    "com.instagram.android", "com.facebook.katana", "com.twitter.android",
                    "com.snapchat.android", "com.tiktok.musically", "com.linkedin.android",
                    "com.reddit.frontpage"
                ],
                "priority": 2
            },
            "media": {
                "apps": [
                    "com.spotify.music", "com.netflix.mediaclient", "com.youtube.android",
                    "com.soundcloud.android", "com.coffeebeanventures.easyvoicerecorder",
                    "com.google.android.apps.photos", "com.amazon.mp3"
                ],
                "priority": 2
            },
            "productivity": {
                "apps": [
                    "com.google.android.keep", "com.evernote", "com.microsoft.office.onenote",
                    "com.todoist", "com.any.do", "com.dropbox.android", "com.notion.id"
                ],
                "priority": 1
            },
            "email": {
                "apps": [
                    "com.google.android.gm", "com.microsoft.office.outlook",
                    "com.yahoo.mobile.client.android.mail", "com.apple.android.mail"
                ],
                "priority": 2
            },
            "navigation": {
                "apps": [
                    "net.daum.android.map", "com.google.android.apps.maps", "com.waze",
                    "com.here.app.maps"
                ],
                "priority": 3
            },
            "system": {
                "apps": [
                    "com.google.android.gms", "com.android.vending", "com.samsung", 
                    "com.sec.", "android", "com.google.android.gsf"
                ],
                "priority": 4
            }
        }
    
    def has_korean_text(self, text):
        """텍스트에 한글이 포함되어 있는지 확인"""
        if not text:
            return False
        
        # 텍스트를 문자열로 변환
        text_str = str(text)
        
        # 한글 유니코드 범위 확인 (가-힣: 44032-55203)
        korean_pattern = re.compile(r'[가-힣]')
        has_korean = bool(korean_pattern.search(text_str))
        
        # 디버깅: 한글이 발견된 경우 샘플 출력
        if has_korean:
            # 한글 부분만 추출하여 샘플 표시
            korean_chars = korean_pattern.findall(text_str)
            sample_text = ''.join(korean_chars[:10])  # 처음 10개 한글 문자만
            print(f"DEBUG: 한글 텍스트 발견: '{sample_text}'... (전체 길이: {len(text_str)})")
        
        return has_korean
    
    def has_email_pattern(self, text):
        """텍스트에 이메일 패턴이 있는지 확인"""
        if not text:
            return False
        email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        return bool(email_pattern.search(str(text)))
    
    def count_korean_chars(self, text):
        """텍스트의 한글 문자 수를 세기"""
        if not text:
            return 0
        korean_pattern = re.compile(r'[가-힣]')
        return len(korean_pattern.findall(str(text)))
    
    def extract_emails(self, text):
        """텍스트에서 이메일 주소 추출"""
        if not text:
            return []
        email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        return email_pattern.findall(str(text))
    
    def analyze_table_content(self, table_info):
        """테이블 내용을 분석하여 한글/이메일 정보 추가"""
        korean_count = 0
        email_count = 0
        has_korean = False
        has_email = False
        
        if table_info.get("rows"):
            for row in table_info["rows"]:
                for cell in row:
                    cell_str = str(cell) if cell is not None else ""
                    if self.has_korean_text(cell_str):
                        has_korean = True
                        korean_count += self.count_korean_chars(cell_str)
                    if self.has_email_pattern(cell_str):
                        has_email = True
                        email_count += len(self.extract_emails(cell_str))
        
        # 디버깅 정보 추가
        if has_korean:
            print(f"DEBUG: 테이블 {table_info.get('table', 'Unknown')}에서 한글 데이터 발견")
            print(f"DEBUG: 한글 문자 수: {korean_count}")
            print(f"DEBUG: 샘플 행 수: {len(table_info.get('rows', []))}")
        
        table_info["has_korean"] = has_korean
        table_info["has_email"] = has_email
        table_info["korean_count"] = korean_count
        table_info["email_count"] = email_count
        
        return table_info
    
    def find_database_files(self, mount_point):
        """개선된 DB 검색 - 서드파티 앱 우선, 다중 검색 방법 사용"""
        db_paths = []
        root_data = os.path.join(mount_point, "data")
        
        if not os.path.exists(root_data):
            self.log_and_print(f"[경고] /data 폴더가 존재하지 않습니다: {root_data}")
            return []
        
        self.log_and_print("[+] 데이터베이스 파일 검색 중...")
        self.log_and_print(f"[+] 검색 경로: {root_data}")
        
        app_categories = self.get_app_categories()
        
        # 1단계: 직접 ls를 이용한 앱 폴더 검색
        self.log_and_print("\n[+] 1단계: 앱 폴더 직접 검색...")
        app_folders = []
        try:
            self.log_and_print(f"    🔍 {root_data} 디렉토리 검색 중...")
            
            ls_result = subprocess.run(
                ["sudo", "ls", "-la", root_data],
                capture_output=True, text=True, timeout=30
            )
            
            if ls_result.returncode == 0:
                lines = ls_result.stdout.strip().split('\n')
                self.log_and_print(f"      📁 디렉토리 항목 수: {len(lines)}개")
                
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 9 and parts[0].startswith('d'):  # 디렉토리만
                        folder_name = parts[-1]
                        if '.' in folder_name and folder_name not in ['.', '..']:  # 패키지명 형태
                            full_path = os.path.join(root_data, folder_name)
                            app_folders.append((folder_name, full_path))
                
                self.log_and_print(f"      ✅ 발견된 앱 폴더: {len(app_folders)}개")
                
                # 처음 몇 개 앱 이름 표시
                if app_folders:
                    sample_apps = [name for name, _ in app_folders[:5]]
                    self.log_and_print(f"      📱 샘플 앱: {', '.join(sample_apps)}")
                    if len(app_folders) > 5:
                        self.log_and_print(f"      ... 및 {len(app_folders) - 5}개 더")
                
            else:
                self.log_and_print(f"      ❌ ls 명령 실패: {ls_result.stderr.strip()}")
                
        except subprocess.TimeoutExpired:
            self.log_and_print(f"      ⏰ 앱 폴더 검색 타임아웃")
        except Exception as e:
            self.log_and_print(f"      ❌ 앱 폴더 검색 오류: {e}")
        
        # 2단계: 서드파티 앱 우선 DB 검색
        self.log_and_print(f"\n[+] 2단계: 서드파티 앱 우선 개별 검사...")
        
        db_info_list = []
        
        # 우선순위 앱들을 먼저 검사
        priority_apps = []
        for category, info in app_categories.items():
            if info["priority"] <= 2:  # 고우선순위만
                for app_pattern in info["apps"]:
                    for app_name, folder_path in app_folders:
                        if app_pattern in app_name:
                            priority_apps.append((app_name, folder_path, category, info["priority"]))
        
        self.log_and_print(f"  우선 검사할 서드파티 앱: {len(priority_apps)}개")
        
        # 우선순위 앱들 개별 검사
        for app_name, app_path, category, priority in priority_apps:
            self.log_and_print(f"    🔍 {app_name} 개별 검사...")
            
            # databases 폴더 직접 확인
            databases_path = os.path.join(app_path, "databases")
            try:
                ls_db_result = subprocess.run(
                    ["sudo", "ls", "-la", databases_path],
                    capture_output=True, text=True, timeout=10
                )
                
                if ls_db_result.returncode == 0:
                    self.log_and_print(f"      ✓ databases 폴더 발견")
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
                                self.log_and_print(f"        🗃️  {filename} ({size_bytes} bytes)")
                    
                    if db_count == 0:
                        self.log_and_print(f"      ⚠️  databases 폴더가 비어있음")
                else:
                    self.log_and_print(f"      ❌ databases 폴더 없음")
                    
            except Exception as e:
                self.log_and_print(f"      ❌ 검사 실패: {e}")
        
        # 우선순위 기준으로 정렬 (서드파티 앱 우선)
        db_info_list.sort(key=lambda x: (x["priority"], -x["size_bytes"]))
        
        # 결과 출력 및 경로 리스트 생성
        if db_info_list:
            self.log_and_print(f"\n[+] DB 파일 분석 우선순위:")
            current_category = None
            
            for db_info in db_info_list:
                if db_info["category"] != current_category:
                    current_category = db_info["category"]
                    self.log_and_print(f"\n  📊 {current_category.upper()}:")
                
                size_kb = db_info["size_bytes"] / 1024 if db_info["size_bytes"] > 0 else 0
                marker = "🔥" if db_info["priority"] <= 2 else "  "
                self.log_and_print(f"{marker} {db_info['app_name']}/{db_info['db_name']} ({size_kb:.1f} KB)")
                
                db_paths.append(db_info["path"])
            
            # 통계 출력
            total_size = sum(db["size_bytes"] for db in db_info_list)
            high_priority_count = sum(1 for db in db_info_list if db["priority"] <= 2)
            
            self.log_and_print(f"\n[+] 총 {len(db_info_list)}개 DB 파일 발견")
            self.log_and_print(f"[+] 총 DB 파일 크기: {total_size / 1024 / 1024:.2f} MB")
            self.log_and_print(f"[+] 고우선순위 서드파티 앱 DB: {high_priority_count}개 ⭐")
        else:
            self.log_and_print(f"[경고] DB 파일을 찾을 수 없습니다")
        
        return db_paths
    
    def get_important_tables_by_app(self, app_name):
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
            "com.discord": ["message", "channel", "guild", "user"],
            "org.telegram.messenger": ["message", "chat", "contact", "media"]
        }
        
        # 패턴 매칭으로 앱 찾기
        for app_pattern, patterns in table_patterns.items():
            if app_pattern in app_name:
                return patterns
        
        return None  # 모든 테이블 분석
    
    def analyze_sqlite_db(self, db_path, app_name=None, row_limit=10):
        """개선된 DB 분석 - 앱별 중요 테이블 우선, 한글/이메일 데이터 분석"""
        summary = []
        copied_db = None
        
        try:
            # DB 파일을 임시 디렉토리에 복사
            if self.temp_dir:
                copied_db = self.copy_db_with_sudo(db_path, self.temp_dir)
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
            important_patterns = self.get_important_tables_by_app(app_name) if app_name else None
            
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
                self.log_and_print(f"    📋 중요 테이블: {len(important_tables)}개, 기타: {len(other_tables)}개")
            else:
                table_names = all_tables
                self.log_and_print(f"    📋 전체 테이블: {len(all_tables)}개")
            
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
                    table_info = self.analyze_table_content(table_info)
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
    
    def generate_html_forensic_report(self, db_summaries, output_path, mount_point):
        """HTML 포렌식 증거 보고서 생성"""
        app_categories = self.get_app_categories()
        
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
                                emails = self.extract_emails(cell_str)
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
    <title>통합 포렌식 분석 보고서</title>
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
            <h1>🔍 통합 디지털 포렌식 분석 보고서</h1>
            <h2>Android FBE 복호화 + WearOS 데이터베이스 분석</h2>
            <p>작업자: {self.metadata.get('worker', 'Unknown')} | 분석일시: {self.start_time.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}</p>
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
            
            # 포렌식 의미 결정
            if item["korean_data"]:
                forensic_meaning = "사용자의 한국어 텍스트 입력 패턴 및 개인 정보 확인 가능"
                forensic_class = "forensic-critical"
            elif item["email_data"]:
                forensic_meaning = "계정 연동 정보 및 외부 서비스 이용 현황 파악 가능"
                forensic_class = "forensic-important"
            elif "messaging" in item["category"]:
                forensic_meaning = "메시징 활동 및 커뮤니케이션 패턴 분석 가능"
                forensic_class = "forensic-important"
            elif "productivity" in item["category"]:
                forensic_meaning = "개인 메모 및 업무 관련 활동 내역 확인 가능"
                forensic_class = "forensic-useful"
            else:
                forensic_meaning = "시스템 사용 패턴 및 앱 활동 로그 분석 가능"
                forensic_class = "forensic-useful"
            
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
                    </div>
                    
                    <!-- 메타데이터 정보 -->
                    <div style="background: #f1f5f9; padding: 12px; border-radius: 6px; margin-bottom: 15px; font-size: 0.9em;">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                            <div><strong>카테고리:</strong> {item["category"]}</div>
                            <div><strong>우선순위:</strong> {priority_text}</div>
                            <div><strong>DB 경로:</strong> {item["db_path"]}</div>
                            <div><strong>총 테이블:</strong> {len(item["important_tables"]) + len(item.get("other_tables", []))}개</div>
                        </div>
                    </div>
                    
                    <!-- 데이터 분류 요약 -->
                    <div style="margin-bottom: 15px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <strong>📊 데이터 분류</strong>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px;">
                            {f'<div style="background: #fef3c7; padding: 8px; border-radius: 4px; text-align: center; color: #92400e; font-size: 0.85em;"><strong>한글</strong><br>{len(item["korean_data"])}개 테이블</div>' if item["korean_data"] else ''}
                            {f'<div style="background: #dbeafe; padding: 8px; border-radius: 4px; text-align: center; color: #1e40af; font-size: 0.85em;"><strong>이메일</strong><br>{len(item["email_data"])}개 테이블</div>' if item["email_data"] else ''}
                            {f'<div style="background: #d1fae5; padding: 8px; border-radius: 4px; text-align: center; color: #065f46; font-size: 0.85em;"><strong>중요</strong><br>{len(item["important_tables"])}개 테이블</div>' if item["important_tables"] else ''}
                            {f'<div style="background: #f3f4f6; padding: 8px; border-radius: 4px; text-align: center; color: #374151; font-size: 0.85em;"><strong>기타</strong><br>{len(item.get("other_tables", []))}개 테이블</div>' if item.get("other_tables") else ''}
                        </div>
                    </div>"""
            
            # 한글 데이터가 있는 경우
            if item["korean_data"]:
                html_content += '''
                    <div style="margin-bottom: 15px;">
                        <strong>🇰🇷 한글 데이터</strong>
                    </div>'''
                
                for table in item["korean_data"][:3]:  # 최대 3개 테이블만 표시
                    html_content += f'''
                    <div style="background: #fef3c7; padding: 12px; border-radius: 6px; margin-bottom: 10px; border-left: 4px solid #f59e0b;">
                        <div style="font-weight: bold; margin-bottom: 8px; color: #92400e;">
                            📋 {table["table"]} ({table["row_count"]}행)
                        </div>'''
                    
                    # 실제 데이터 내용 표시
                    if table.get("rows") and len(table["rows"]) > 0:
                        html_content += '<div style="margin-left: 10px;">'
                        for i, row in enumerate(table["rows"][:5]):  # 최대 5행만 표시
                            row_text = " | ".join([str(cell) if cell is not None else "NULL" for cell in row])
                            if len(row_text) > 100:  # 긴 텍스트는 자르기
                                row_text = row_text[:100] + "..."
                            html_content += f'<div style="margin-bottom: 4px; font-size: 0.9em;">• {row_text}</div>'
                        if table["row_count"] > 5:
                            html_content += f'<div style="color: #92400e; font-size: 0.8em; font-style: italic;">... 및 {table["row_count"] - 5}개 더</div>'
                        html_content += '</div>'
                    
                    html_content += '</div>'
                    html_content += f'''
                    <div class="data-item korean-data">
                        <strong>{table["table"]}</strong> ({table["row_count"]}행)
                    </div>'''
            
            # 이메일 데이터가 있는 경우
            if item["email_data"]:
                html_content += '''
                    <div style="margin-bottom: 15px;">
                        <strong>📧 이메일 관련 데이터</strong>
                    </div>'''
                
                for table in item["email_data"][:2]:  # 최대 2개 테이블만 표시
                    html_content += f'''
                    <div style="background: #dbeafe; padding: 12px; border-radius: 6px; margin-bottom: 10px; border-left: 4px solid #3b82f6;">
                        <div style="font-weight: bold; margin-bottom: 8px; color: #1e40af;">
                            📧 {table["table"]} ({table["row_count"]}행)
                        </div>'''
                    
                    # 실제 데이터 내용 표시
                    if table.get("rows") and len(table["rows"]) > 0:
                        html_content += '<div style="margin-left: 10px;">'
                        for i, row in enumerate(table["rows"][:5]):  # 최대 5행만 표시
                            row_text = " | ".join([str(cell) if cell is not None else "NULL" for cell in row])
                            if len(row_text) > 100:  # 긴 텍스트는 자르기
                                row_text = row_text[:100] + "..."
                            html_content += f'<div style="margin-bottom: 4px; font-size: 0.9em;">• {row_text}</div>'
                        if table["row_count"] > 5:
                            html_content += f'<div style="color: #1e40af; font-size: 0.8em; font-style: italic;">... 및 {table["row_count"] - 5}개 더</div>'
                        html_content += '</div>'
                    
                    html_content += '</div>'
                    html_content += f'''
                    <div class="data-item email-data">
                        <strong>{table["table"]}</strong> ({table["row_count"]}행)
                    </div>'''
            
            # 기타 중요 데이터
            if item["important_tables"] and not item["korean_data"] and not item["email_data"]:
                html_content += '''
                    <div style="margin-bottom: 15px;">
                        <strong>📊 주요 테이블</strong>
                    </div>'''
                
                for table in item["important_tables"][:3]:
                    html_content += f'''
                    <div class="data-item">
                        <strong>{table["table"]}</strong> ({table["row_count"]}행)
                    </div>'''
            
            # 포렌식 의미 설명
            html_content += f'''
                    <div class="{forensic_class} forensic-note">
                        📍 <strong>포렌식 의미:</strong> {forensic_meaning}
                    </div>
                    
                    <!-- 상세 데이터 표시 -->
                    <div class="detailed-data">
                        <details>
                            <summary style="cursor: pointer; color: #3b82f6; font-weight: bold; margin: 15px 0 10px 0;">
                                🔍 상세 데이터 보기
                            </summary>
                            <div style="background: #f8fafc; padding: 15px; border-radius: 8px; margin-top: 10px;">'''
            
            # 한글 데이터 상세 표시
            if item["korean_data"]:
                html_content += '''
                                <div style="margin-bottom: 20px;">
                                    <h4 style="color: #f59e0b; margin-bottom: 10px;">🇰🇷 한글 데이터 상세</h4>'''
                
                for table in item["korean_data"][:3]:  # 최대 3개 테이블
                    html_content += f'''
                                    <div style="background: #fef3c7; padding: 12px; border-radius: 6px; margin-bottom: 10px;">
                                        <strong style="color: #92400e;">테이블: {table["table"]}</strong>
                                        <div style="color: #92400e; font-size: 0.9em; margin: 5px 0;">행 수: {table["row_count"]:,}개 | 한글 문자: {table.get("korean_count", 0):,}자</div>
                                        <div style="color: #92400e; font-size: 0.9em; margin: 5px 0;">컬럼: {", ".join(table.get("columns", [])[:5])}{"..." if len(table.get("columns", [])) > 5 else ""}</div>'''
                    
                    # 실제 데이터 샘플 표시 (한글 포함된 행만)
                    if table.get("rows"):
                        korean_samples = []
                        for row in table["rows"][:10]:  # 최대 10개 행에서 검색
                            row_has_korean = any(self.has_korean_text(str(cell)) for cell in row if cell is not None)
                            if row_has_korean:
                                korean_samples.append(row)
                        
                        if korean_samples:
                            html_content += '''
                                        <div style="margin-top: 8px;">
                                            <strong style="color: #92400e;">한글 데이터 샘플:</strong>'''
                            for i, sample_row in enumerate(korean_samples[:5]):  # 최대 5개 샘플
                                # 한글 포함된 셀만 강조하여 표시
                                highlighted_row = []
                                for j, cell in enumerate(sample_row):
                                    if cell is not None and self.has_korean_text(str(cell)):
                                        cell_str = str(cell)
                                        # 한글 부분을 강조
                                        highlighted_cell = f'<span style="background: #fef3c7; padding: 2px 4px; border-radius: 3px; font-weight: bold;">{cell_str}</span>'
                                        highlighted_row.append(f'컬럼{j+1}: {highlighted_cell}')
                                    else:
                                        cell_str = str(cell) if cell is not None else "NULL"
                                        highlighted_row.append(f'컬럼{j+1}: {cell_str}')
                                
                                row_display = " | ".join(highlighted_row)
                                html_content += f'''
                                            <div style="background: white; padding: 8px; margin: 5px 0; border-radius: 4px; font-family: monospace; font-size: 0.85em; color: #374151;">
                                                <strong>샘플 {i+1}:</strong><br>
                                                {row_display[:300]}{"..." if len(row_display) > 300 else ""}
                                            </div>'''
                            html_content += '''
                                        </div>'''
                        else:
                            # 한글 데이터가 없다면 전체 데이터 샘플 표시
                            html_content += '''
                                        <div style="margin-top: 8px;">
                                            <strong style="color: #92400e;">전체 데이터 샘플 (한글 미포함):</strong>'''
                            for i, sample_row in enumerate(table["rows"][:3]):  # 최대 3개 샘플
                                html_content += f'''
                                            <div style="background: white; padding: 8px; margin: 5px 0; border-radius: 4px; font-family: monospace; font-size: 0.85em; color: #374151;">
                                                <strong>샘플 {i+1}:</strong><br>
                                                {str(sample_row)[:250]}{"..." if len(str(sample_row)) > 250 else ""}
                                            </div>'''
                            html_content += '''
                                        </div>'''
                    
                    # 테이블 스키마 상세 정보
                    if table.get("columns"):
                        html_content += '''
                                        <div style="margin-top: 8px;">
                                            <strong style="color: #92400e;">테이블 스키마:</strong>
                                            <div style="background: white; padding: 8px; margin: 5px 0; border-radius: 4px; font-family: monospace; font-size: 0.8em; color: #374151; max-height: 100px; overflow-y: auto;">'''
                        
                        for j, col in enumerate(table["columns"][:8]):  # 최대 8개 컬럼
                            html_content += f'''
                                                {j+1:2d}. {col}'''
                        
                        if len(table["columns"]) > 8:
                            html_content += f'''
                                                ... 및 {len(table["columns"]) - 8}개 더'''
                        
                        html_content += '''
                                            </div>
                                        </div>'''
                    
                    # 원본 데이터 표시 (한글 데이터가 있는 경우)
                    if table.get("has_korean") and table.get("rows"):
                        html_content += '''
                                        <div style="margin-top: 12px;">
                                            <strong style="color: #92400e;">🔍 원본 한글 데이터 상세:</strong>
                                            <div style="background: #fef3c7; padding: 10px; border-radius: 6px; margin-top: 8px; border: 1px solid #f59e0b;">'''
                        
                        # 한글 포함된 행들을 찾아서 상세 표시
                        korean_rows = []
                        for row_idx, row in enumerate(table["rows"][:20]):  # 최대 20개 행 검사
                            row_has_korean = False
                            korean_cells = []
                            
                            for col_idx, cell in enumerate(row):
                                if cell is not None and self.has_korean_text(str(cell)):
                                    row_has_korean = True
                                    cell_str = str(cell)
                                    # 한글 부분만 추출
                                    korean_chars = re.findall(r'[가-힣]', cell_str)
                                    korean_cells.append(f'컬럼{col_idx+1}: {"".join(korean_chars)}')
                            
                            if row_has_korean:
                                korean_rows.append((row_idx, korean_cells))
                        
                        if korean_rows:
                            for i, (row_idx, korean_cells) in enumerate(korean_rows[:5]):  # 최대 5개 행
                                html_content += f'''
                                            <div style="background: white; padding: 8px; margin: 5px 0; border-radius: 4px; font-size: 0.85em;">
                                                <strong>행 {row_idx+1} (한글 포함):</strong><br>
                                                <span style="color: #92400e; font-weight: bold;">{", ".join(korean_cells)}</span>
                                            </div>'''
                        else:
                            html_content += '''
                                            <div style="background: white; padding: 8px; margin: 5px 0; border-radius: 4px; font-size: 0.85em; color: #6b7280;">
                                                한글 데이터를 찾을 수 없습니다.
                                            </div>'''
                        
                        html_content += '''
                                            </div>
                                        </div>'''
                    
                    html_content += '''
                                    </div>'''
            
            # 이메일 데이터 상세 표시
            if item["email_data"]:
                html_content += '''
                                <div style="margin-bottom: 20px;">
                                    <h4 style="color: #3b82f6; margin-bottom: 10px;">📧 이메일 데이터 상세</h4>'''
                
                for table in item["email_data"][:2]:  # 최대 2개 테이블
                    html_content += f'''
                                    <div style="background: #dbeafe; padding: 12px; border-radius: 6px; margin-bottom: 10px;">
                                        <strong style="color: #1e40af;">테이블: {table["table"]}</strong>
                                        <div style="color: #1e40af; font-size: 0.9em; margin: 5px 0;">행 수: {table["row_count"]:,}개 | 이메일: {table.get("email_count", 0):,}개</div>
                                        <div style="color: #1e40af; font-size: 0.9em; margin: 5px 0;">컬럼: {", ".join(table.get("columns", [])[:5])}{"..." if len(table.get("columns", [])) > 5 else ""}</div>'''
                    
                    # 이메일 패턴 샘플 표시
                    if table.get("rows"):
                        email_samples = []
                        email_rows = []
                        
                        for row_idx, row in enumerate(table["rows"][:10]):  # 최대 10개 행
                            row_emails = []
                            for col_idx, cell in enumerate(row):
                                if cell is not None:
                                    emails = self.extract_emails(str(cell))
                                    if emails:
                                        email_samples.extend(emails[:2])  # 각 셀에서 최대 2개
                                        row_emails.append((col_idx, emails[0]))  # 첫 번째 이메일만
                                        if len(email_samples) >= 8:  # 총 최대 8개
                                            break
                            if row_emails:
                                email_rows.append((row_idx, row_emails))
                            if len(email_samples) >= 8:
                                break
                        
                        if email_samples:
                            html_content += '''
                                        <div style="margin-top: 8px;">
                                            <strong style="color: #1e40af;">이메일 주소 샘플:</strong>'''
                            for email in email_samples[:8]:
                                html_content += f'''
                                            <div style="background: white; padding: 6px; margin: 3px 0; border-radius: 4px; font-family: monospace; font-size: 0.85em; color: #374151;">
                                                {email}
                                            </div>'''
                            html_content += '''
                                        </div>'''
                        
                        # 이메일이 포함된 행의 실제 데이터 표시
                        if email_rows:
                            html_content += '''
                                        <div style="margin-top: 8px;">
                                            <strong style="color: #1e40af;">이메일 포함 데이터 샘플:</strong>'''
                            for i, (row_idx, row_emails) in enumerate(email_rows[:3]):  # 최대 3개 행
                                html_content += f'''
                                            <div style="background: white; padding: 8px; margin: 5px 0; border-radius: 4px; font-family: monospace; font-size: 0.85em; color: #374151;">
                                                <strong>행 {row_idx+1}:</strong><br>'''
                                
                                # 전체 행 데이터 표시 (이메일 부분 강조)
                                row_display = []
                                for col_idx, cell in enumerate(table["rows"][row_idx]):
                                    if cell is not None:
                                        cell_str = str(cell)
                                        # 이메일이 포함된 컬럼인지 확인
                                        if any(col_idx == email_col for email_col, _ in row_emails):
                                            # 이메일 부분을 강조
                                            highlighted_cell = f'<span style="background: #dbeafe; padding: 2px 4px; border-radius: 3px; font-weight: bold; color: #1e40af;">{cell_str}</span>'
                                            row_display.append(f'컬럼{col_idx+1}: {highlighted_cell}')
                                        else:
                                            row_display.append(f'컬럼{col_idx+1}: {cell_str}')
                                    else:
                                        row_display.append(f'컬럼{col_idx+1}: NULL')
                                
                                row_text = " | ".join(row_display)
                                html_content += f'''
                                                {row_text[:300]}{"..." if len(row_text) > 300 else ""}
                                            </div>'''
                            html_content += '''
                                        </div>'''
                    
                    html_content += '''
                                    </div>'''
                
                html_content += '''
                                </div>'''
            
            # 기타 중요 테이블 상세 표시
            if item["important_tables"] and not item["korean_data"] and not item["email_data"]:
                html_content += '''
                                <div style="margin-bottom: 20px;">
                                    <h4 style="color: #059669; margin-bottom: 10px;">📊 주요 테이블 상세</h4>'''
                
                for table in item["important_tables"][:3]:
                    html_content += f'''
                                    <div style="background: #d1fae5; padding: 12px; border-radius: 6px; margin-bottom: 10px;">
                                        <strong style="color: #065f46;">테이블: {table["table"]}</strong>
                                        <div style="color: #065f46; font-size: 0.9em; margin: 5px 0;">행 수: {table["row_count"]:,}개</div>
                                        <div style="color: #065f46; font-size: 0.9em; margin: 5px 0;">컬럼: {", ".join(table.get("columns", [])[:6])}{"..." if len(table.get("columns", [])) > 6 else ""}</div>'''
                    
                    # 데이터 샘플 표시
                    if table.get("rows"):
                        html_content += '''
                                        <div style="margin-top: 8px;">
                                            <strong style="color: #065f46;">데이터 샘플:</strong>'''
                        for i, sample_row in enumerate(table["rows"][:2]):  # 최대 2개 샘플
                            html_content += f'''
                                            <div style="background: white; padding: 8px; margin: 5px 0; border-radius: 4px; font-family: monospace; font-size: 0.85em; color: #374151;">
                                                샘플 {i+1}: {str(sample_row)[:150]}{"..." if len(str(sample_row)) > 150 else ""}
                                            </div>'''
                        html_content += '''
                                        </div>'''
                    
                    # 테이블 스키마 상세 정보
                    if table.get("columns"):
                        html_content += '''
                                        <div style="margin-top: 8px;">
                                            <strong style="color: #065f46;">테이블 스키마:</strong>
                                            <div style="background: white; padding: 8px; margin: 5px 0; border-radius: 4px; font-family: monospace; font-size: 0.8em; color: #374151; max-height: 100px; overflow-y: auto;">'''
                        
                        for j, col in enumerate(table["columns"][:8]):  # 최대 8개 컬럼
                            html_content += f'''
                                                {j+1:2d}. {col}'''
                        
                        if len(table["columns"]) > 8:
                            html_content += f'''
                                                ... 및 {len(table["columns"]) - 8}개 더'''
                        
                        html_content += '''
                                            </div>
                                        </div>'''
                    
                    html_content += '''
                                    </div>'''
                
                html_content += '''
                                </div>'''
            
            # 모든 테이블 요약 정보
            html_content += '''
                                <div style="margin-top: 20px; background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0;">
                                    <h4 style="color: #374151; margin-bottom: 12px;">📋 전체 테이블 요약</h4>
                                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">'''
            
            # 중요 테이블 요약
            if item["important_tables"]:
                html_content += f'''
                                        <div style="background: #d1fae5; padding: 10px; border-radius: 6px;">
                                            <strong style="color: #065f46;">중요 테이블 ({len(item["important_tables"])}개)</strong>
                                            <div style="font-size: 0.85em; color: #065f46; margin-top: 5px;">'''
                
                for table in item["important_tables"][:5]:  # 최대 5개
                    html_content += f'''
                                                • {table["table"]} ({table["row_count"]:,}행)'''
                
                if len(item["important_tables"]) > 5:
                    html_content += f'''
                                                ... 및 {len(item["important_tables"]) - 5}개 더'''
                
                html_content += '''
                                            </div>
                                        </div>'''
            
            # 기타 테이블 요약
            if item.get("other_tables"):
                html_content += f'''
                                        <div style="background: #f3f4f6; padding: 10px; border-radius: 6px;">
                                            <strong style="color: #374151;">기타 테이블 ({len(item["other_tables"])}개)</strong>
                                            <div style="font-size: 0.85em; color: #374151; margin-top: 5px;">'''
                
                for table in item["other_tables"][:5]:  # 최대 5개
                    html_content += f'''
                                                • {table["table"]} ({table["row_count"]:,}행)'''
                
                if len(item["other_tables"]) > 5:
                    html_content += f'''
                                                ... 및 {len(item["other_tables"]) - 5}개 더'''
                
                html_content += '''
                                            </div>
                                        </div>'''
            
            html_content += '''
                                    </div>
                                </div>'''
            
            # 포렌식 분석 가이드
            html_content += '''
                                <div style="background: #fef2f2; padding: 12px; border-radius: 6px; margin-top: 15px; border-left: 4px solid #dc2626;">
                                    <strong style="color: #dc2626;">🔍 포렌식 분석 가이드:</strong>
                                    <ul style="margin: 8px 0 0 20px; color: #991b1b; font-size: 0.9em;">
                                        <li>이 데이터는 법적 증거로 활용 가능</li>
                                        <li>사용자 활동 패턴 및 시간대 분석 가능</li>
                                        <li>계정 연동 정보 및 외부 서비스 이용 현황 파악</li>
                                        <li>개인정보 및 민감한 데이터 포함 가능성 있음</li>
                                    </ul>
                                </div>
                                
                                <!-- 추가 분석 정보 -->
                                <div style="margin-top: 15px; background: #f0f9ff; padding: 12px; border-radius: 6px; border-left: 4px solid #0ea5e9;">
                                    <strong style="color: #0c4a6e;">📋 추가 분석 정보:</strong>
                                    <div style="margin-top: 8px; font-size: 0.9em; color: #0c4a6e;">
                                        <div><strong>• 앱 패키지:</strong> {item["app_name"]}</div>
                                        <div><strong>• 데이터베이스 경로:</strong> /data/{item["db_path"]}</div>
                                        <div><strong>• 우선순위 레벨:</strong> {item["priority"]} (1: 핵심, 2: 중요, 3: 참고)</div>
                                        <div><strong>• 카테고리:</strong> {item["category"]}</div>
                                    </div>
                                </div>
                                
                                <!-- 데이터 품질 지표 -->
                                <div style="margin-top: 15px; background: #f0fdf4; padding: 12px; border-radius: 6px; border-left: 4px solid #16a34a;">
                                    <strong style="color: #166534;">📊 데이터 품질 지표:</strong>
                                    <div style="margin-top: 8px; font-size: 0.9em; color: #166534;">
                                        <div><strong>• 데이터 밀도:</strong> {item["total_rows"] / max(len(item["important_tables"]) + len(item.get("other_tables", [])), 1):.1f} 행/테이블</div>
                                        <div><strong>• 한글 데이터 비율:</strong> {sum(t.get("korean_count", 0) for t in item.get("korean_data", [])) / max(item["total_rows"], 1) * 100:.1f}%</div>
                                        <div><strong>• 이메일 데이터 비율:</strong> {sum(t.get("email_count", 0) for t in item.get("email_data", [])) / max(item["total_rows"], 1) * 100:.1f}%</div>
                                        <div><strong>• 중요 테이블 비율:</strong> {len(item["important_tables"]) / max(len(item["important_tables"]) + len(item.get("other_tables", [])), 1) * 100:.1f}%</div>
                                    </div>
                                </div>
                            </div>
                        </details>
                    </div>
                </div>
            </div>'''
        
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
            
            <!-- 상세 통계 -->
            <div style="margin-top: 25px; text-align: left; background: rgba(255,255,255,0.1); padding: 20px; border-radius: 15px;">
                <h4 style="color: #fbbf24; margin-bottom: 15px; text-align: center;">📈 상세 분석 통계</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px;">
                    <div>
                        <h5 style="color: #60a5fa; margin-bottom: 8px;">🔍 데이터베이스 분석</h5>
                        <ul style="color: #e5e7eb; font-size: 0.9em; margin-left: 20px;">
                            <li>분석된 DB: {total_dbs}개</li>
                            <li>데이터 포함 테이블: {tables_with_data}개</li>
                            <li>전체 테이블: {total_tables}개</li>
                        </ul>
                    </div>
                    <div>
                        <h5 style="color: #fbbf24; margin-bottom: 8px;">🇰🇷 한글 데이터</h5>
                        <ul style="color: #e5e7eb; font-size: 0.9em; margin-left: 20px;">
                            <li>한글 포함 테이블: {korean_tables}개</li>
                            <li>총 한글 문자: {total_korean_chars:,}자</li>
                            <li>한글 데이터 비율: {(total_korean_chars / max(total_rows, 1) * 100):.1f}%</li>
                        </ul>
                    </div>
                    <div>
                        <h5 style="color: #34d399; margin-bottom: 8px;">📧 이메일 데이터</h5>
                        <ul style="color: #e5e7eb; font-size: 0.9em; margin-left: 20px;">
                            <li>이메일 포함 테이블: {email_tables}개</li>
                            <li>총 이메일 주소: {total_emails:,}개</li>
                            <li>주요 계정: {main_account or "미확인"}</li>
                        </ul>
                    </div>
                </div>
            </div>
            
            <!-- 포렌식 분석 권고사항 -->
            <div style="margin-top: 25px; background: rgba(239, 68, 68, 0.2); padding: 20px; border-radius: 15px; border-left: 4px solid #ef4444;">
                <h4 style="color: #fca5a5; margin-bottom: 15px;">⚠️ 포렌식 분석 권고사항</h4>
                <div style="color: #fecaca; text-align: left; font-size: 0.95em;">
                    <div style="margin-bottom: 12px;">
                        <strong>🔒 데이터 보안:</strong>
                        <ul style="margin: 8px 0 0 20px;">
                            <li>이미지 파일은 안전한 보관소에 백업 보관</li>
                            <li>분석 결과는 암호화하여 저장</li>
                            <li>접근 권한을 제한하고 감사 로그 유지</li>
                        </ul>
                    </div>
                    <div style="margin-bottom: 12px;">
                        <strong>🔍 추가 분석 필요:</strong>
                        <ul style="margin: 8px 0 0 20px;">
                            <li>휴대폰 본체의 추가 데이터 분석</li>
                            <li>클라우드 동기화 데이터 수집</li>
                            <li>네트워크 통신 로그 분석</li>
                            <li>타임라인 분석 및 사용자 활동 패턴 추적</li>
                        </ul>
                    </div>
                    <div>
                        <strong>📋 법적 고려사항:</strong>
                        <ul style="margin: 8px 0 0 20px;">
                            <li>개인정보보호법 준수</li>
                            <li>증거 수집 과정의 적법성 확보</li>
                            <li>분석 결과의 신뢰성 및 무결성 검증</li>
                        </ul>
                    </div>
                </div>
            </div>
            
            <div style="margin-top: 20px; padding: 15px; background: rgba(59, 130, 246, 0.2); border-radius: 10px;">
                <strong>🎯 최종 권고:</strong> 휴대폰 본체 및 클라우드 동기화 데이터 추가 분석 필요
            </div>
        </div>
    </div>
</body>
</html>"""
        
        # HTML 파일 저장
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        # 포렌식 분석 통계를 메타데이터에 추가
        self.metadata['forensic_analysis'] = {
            'total_databases': total_dbs,
            'total_tables': total_tables,
            'tables_with_data': tables_with_data,
            'total_rows': total_rows,
            'korean_tables': korean_tables,
            'email_tables': email_tables,
            'total_korean_chars': total_korean_chars,
            'total_emails': total_emails,
            'evidence_items': len(evidence_items),
            'main_account': main_account
        }
    
    def run_forensic_analysis(self, decrypted_file):
        """포렌식 분석 실행"""
        if not os.path.exists(decrypted_file):
            self.log_and_print(f"복호화된 파일이 없습니다: {decrypted_file}")
            return False
        
        self.log_and_print("="*60)
        self.log_and_print("WearOS 포렌식 분석을 시작합니다...")
        self.log_and_print("="*60)
        
        # 임시 작업 디렉토리 생성
        self.temp_dir = tempfile.mkdtemp(prefix="integrated_forensics_")
        self.log_and_print(f"임시 작업 디렉토리: {self.temp_dir}")
        
        # 마운트 포인트 설정
        home = os.path.expanduser("~")
        mount_point = os.path.join(home, "mnt_integrated")
        
        try:
            # 이미지 파일 마운트
            self.log_and_print("🔍 이미지 파일 마운트 시작...")
            self.mount_img(decrypted_file, mount_point)
            self.log_and_print("✅ 이미지 파일 마운트 완료")
            
            # 데이터베이스 파일 검색
            self.log_and_print("\n🔍 데이터베이스 파일 검색 시작...")
            db_files = self.find_database_files(mount_point)
            self.log_and_print(f"✅ 발견된 DB 파일 수: {len(db_files)}")
            
            if not db_files:
                self.log_and_print("⚠️  분석할 DB 파일이 없습니다.")
                self.log_and_print("💡 가능한 원인:")
                self.log_and_print("   - 이미지 파일이 올바르게 마운트되지 않음")
                self.log_and_print("   - /data 폴더가 존재하지 않음")
                self.log_and_print("   - 파일시스템 권한 문제")
                return False
            
            # DB 분석
            db_summaries = {}
            forensic_start = datetime.now(timezone.utc)
            
            self.log_and_print(f"\n🔍 포렌식 DB 분석 시작...")
            self.log_and_print(f"📊 총 {len(db_files)}개 데이터베이스 분석 예정")
            
            successful_analyses = 0
            failed_analyses = 0
            
            for i, db in enumerate(db_files, 1):
                rel_path = os.path.relpath(db, os.path.join(mount_point, "data"))
                app_name = rel_path.split('/')[0]
                
                self.log_and_print(f"\n[{i}/{len(db_files)}] 🔍 분석 중: {rel_path}")
                
                try:
                    db_result = self.analyze_sqlite_db(db, app_name=app_name)
                    if db_result and any(table.get('table') not in ['DB_ERROR', 'COPY_ERROR'] for table in db_result):
                        db_summaries[db] = db_result
                        successful_analyses += 1
                        self.log_and_print(f"      ✅ 분석 완료: {len(db_result)}개 테이블")
                    else:
                        failed_analyses += 1
                        self.log_and_print(f"      ⚠️  분석 실패 또는 빈 결과")
                        
                except Exception as db_error:
                    failed_analyses += 1
                    self.log_and_print(f"      ❌ 분석 중 오류: {db_error}")
                    # 오류가 있어도 계속 진행
                    continue
            
            forensic_end = datetime.now(timezone.utc)
            forensic_duration = (forensic_end - forensic_start).total_seconds()
            
            # 분석 결과 요약
            self.log_and_print(f"\n📊 포렌식 분석 결과 요약:")
            self.log_and_print(f"   ✅ 성공: {successful_analyses}개")
            self.log_and_print(f"   ❌ 실패: {failed_analyses}개")
            self.log_and_print(f"   ⏱️  소요시간: {forensic_duration:.1f}초")
            
            if not db_summaries:
                self.log_and_print("⚠️  분석 가능한 데이터베이스가 없습니다.")
                return False
            
            # HTML 포렌식 보고서 생성
            self.log_and_print(f"\n📄 HTML 포렌식 보고서 생성 중...")
            output_html = os.path.join(home, f"integrated_forensic_report_{self.start_time.strftime('%Y%m%d_%H%M%S')}.html")
            
            try:
                self.generate_html_forensic_report(db_summaries, output_html, mount_point)
                self.log_and_print(f"✅ HTML 보고서 생성 완료: {output_html}")
            except Exception as report_error:
                self.log_and_print(f"❌ HTML 보고서 생성 실패: {report_error}")
                # 보고서 생성 실패해도 분석은 성공으로 간주
                output_html = "생성 실패"
            
            self.metadata['forensic_process'] = {
                'start_time': forensic_start.isoformat(),
                'end_time': forensic_end.isoformat(),
                'duration_seconds': forensic_duration,
                'analyzed_databases': len(db_files),
                'successful_analyses': successful_analyses,
                'failed_analyses': failed_analyses,
                'output_report': output_html
            }
            
            self.log_and_print(f"\n🎯 통합 포렌식 분석 완료!")
            self.log_and_print(f"📊 분석된 DB: {successful_analyses}개")
            self.log_and_print(f"📄 보고서: {output_html}")
            self.log_and_print(f"⏱️  총 소요시간: {forensic_duration:.1f}초")
            
            return True
            
        except Exception as e:
            self.log_and_print(f"❌ 포렌식 분석 중 치명적 오류 발생: {e}")
            self.log_and_print("🔧 문제 해결 방법:")
            self.log_and_print("  1. sudo 권한이 올바르게 설정되었는지 확인")
            self.log_and_print("  2. 이미지 파일이 손상되지 않았는지 확인")
            self.log_and_print("  3. 충분한 디스크 공간이 있는지 확인")
            self.log_and_print("  4. 시스템 로그 확인 (dmesg, /var/log/syslog)")
            
            import traceback
            self.log_and_print(f"\n📋 상세 오류 정보:")
            for line in traceback.format_exc().splitlines():
                self.log_and_print(f"   {line}")
            
            return False
        finally:
            # 정리 작업
            self.umount_img(mount_point)
            if os.path.exists(mount_point):
                shutil.rmtree(mount_point, ignore_errors=True)
            
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.log_and_print(f"[+] 임시 디렉토리 정리 완료")
    
    def finalize_log(self, success=True, forensic_success=False):
        """로그 마무리"""
        end_time = datetime.now(timezone.utc)
        total_duration = (end_time - self.start_time).total_seconds()
        
        self.metadata.update({
            'end_time': end_time.isoformat(),
            'total_duration_seconds': total_duration,
            'decryption_success': success,
            'forensic_success': forensic_success,
            'overall_success': success and forensic_success
        })
        
        # 출력 파일 메타데이터 수집
        output_file = 'userdata-decrypted.img'
        if os.path.exists(output_file):
            self.log_and_print("출력 파일 메타데이터 수집 중...")
            output_metadata = self.collect_file_metadata(output_file)
            if output_metadata:
                self.metadata['output_files'] = {output_file: output_metadata}
        
        # JSON 메타데이터 파일 생성
        metadata_file = f"integrated_metadata_{self.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, indent=2, ensure_ascii=False, default=str)
            self.log_and_print(f"📄 메타데이터 파일 생성: {metadata_file}")
        except Exception as e:
            self.log_and_print(f"메타데이터 파일 생성 실패: {e}")
        
        self.log_and_print("\n" + "="*60)
        self.log_and_print("최종 결과:")
        self.log_and_print("="*60)
        self.log_and_print(f"작업자: {self.metadata.get('worker', 'Unknown')}")
        self.log_and_print(f"시작 시간: {self.metadata['timezone_info']['local']}")
        self.log_and_print(f"종료 시간: {end_time.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.log_and_print(f"총 소요시간: {total_duration:.1f}초")
        self.log_and_print(f"FBE 복호화: {'완료' if success else '실패'}")
        self.log_and_print(f"포렌식 분석: {'완료' if forensic_success else '실패'}")
        self.log_and_print(f"로그 파일: {self.log_file}")
        self.log_and_print(f"메타데이터 파일: {metadata_file}")
        
        # 무결성 검증 결과 출력
        if 'decryption_process' in self.metadata:
            decryption_info = self.metadata['decryption_process']
            if decryption_info.get('original_file_hash') and decryption_info.get('decrypted_file_hash'):
                self.log_and_print("\n" + "="*60)
                self.log_and_print("무결성 검증 결과:")
                self.log_and_print("="*60)
                
                # 원본 파일명 찾기
                original_filename = "userdata-qemu.img.qcow2"  # 기본값
                for filename in ['userdata-qemu.img.qcow2', 'userdata(1).img', 'userdata.img', 'userdata-qemu.img']:
                    if os.path.exists(filename):
                        original_filename = filename
                        break
                
                self.log_and_print(f"원본 파일: {original_filename}")
                self.log_and_print(f"원본 해시: {decryption_info['original_file_hash']}")
                self.log_and_print(f"복호화 파일: userdata-decrypted.img")
                self.log_and_print(f"복호화 해시: {decryption_info['decrypted_file_hash']}")
        
        # 체인 오브 커스터디 보고서 출력
        self.log_and_print("\n" + "="*60)
        self.log_and_print("최종 체인 오브 커스터디 보고서:")
        self.log_and_print("="*60)
        self.log_and_print(f"작업 시작: {self.metadata['timezone_info']['utc']}")
        self.log_and_print(f"작업 종료: {end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        self.log_and_print(f"총 소요시간: {total_duration:.1f}초")
        self.log_and_print(f"최종 상태: {'SUCCESS' if success and forensic_success else 'SUCCESS_WITH_INTEGRITY_WARNING' if success else 'FAILED'}")
        self.log_and_print(f"JSON 보고서 생성: {metadata_file}")
        self.log_and_print(f"체인 오브 커스터디 로그 파일: {self.log_file}")
        self.log_and_print(f"구조화된 보고서: {metadata_file}")
        self.log_and_print("모든 작업이 기록되었습니다.")
        
        if success and forensic_success:
            self.log_and_print("\n🎉 모든 통합 분석이 성공적으로 완료되었습니다!")
            if 'forensic_process' in self.metadata:
                self.log_and_print(f"📊 포렌식 보고서: {self.metadata['forensic_process']['output_report']}")
        elif success:
            self.log_and_print("\n✅ 복호화는 완료되었으나 포렌식 분석에 문제가 있었습니다.")
        else:
            self.log_and_print("\n❌ 복호화 단계에서 실패했습니다.")

def main():
    """통합 Android FBE 복호화 및 WearOS 포렌식 분석 메인 함수"""
    print("DEBUG: 메인 함수 시작")
    logger = IntegratedDecryptionAndForensicsLogger()
    
    try:
        logger.log_and_print("통합 Android FBE 복호화 및 WearOS 포렌식 분석")
        logger.log_and_print("="*60)
        
        # 1. 시스템 정보 수집
        print("DEBUG: 1단계 - 시스템 정보 수집")
        logger.log_and_print("1. 시스템 정보 수집 중...")
        logger.collect_system_info()
        print("DEBUG: 1단계 완료")
        
        # 2. 사전 요구사항 확인
        print("DEBUG: 2단계 - 사전 요구사항 확인")
        logger.log_and_print("\n2. 사전 요구사항 확인 중...")
        if not logger.check_prerequisites():
            logger.log_and_print("\n사전 요구사항이 충족되지 않았습니다.")
            logger.finalize_log(success=False, forensic_success=False)
            sys.exit(1)
        print("DEBUG: 2단계 완료")
        
        # 3. FBE 복호화 실행
        print("DEBUG: 3단계 - FBE 복호화")
        logger.log_and_print("\n3. FBE 복호화 실행 중...")
        decryption_success = logger.run_decryption()
        
        if not decryption_success:
            logger.log_and_print("\n복호화에 실패했습니다.")
            logger.finalize_log(success=False, forensic_success=False)
            sys.exit(1)
        print("DEBUG: 3단계 완료")
        
        # 4. 복호화된 파일 존재 확인
        print("DEBUG: 4단계 - 결과 파일 확인")
        decrypted_file = 'userdata-decrypted.img'
        if not os.path.exists(decrypted_file):
            logger.log_and_print(f"\n복호화된 파일이 생성되지 않았습니다: {decrypted_file}")
            logger.finalize_log(success=True, forensic_success=False)
            sys.exit(1)
        
        logger.log_and_print(f"\n✅ 복호화된 파일 확인: {decrypted_file}")
        print("DEBUG: 4단계 완료")
        
        # 5. 포렌식 분석 실행
        print("DEBUG: 5단계 - 포렌식 분석")
        logger.log_and_print("\n4. WearOS 포렌식 분석 실행 중...")
        
        # Linux 환경 체크 (sudo 명령 필요)
        if platform.system() != 'Linux':
            logger.log_and_print("⚠️  포렌식 분석은 Linux 환경에서만 지원됩니다.")
            logger.log_and_print("현재 OS: " + platform.system())
            logger.log_and_print("복호화는 완료되었으니 Linux 환경에서 별도로 포렌식 분석을 수행하세요.")
            logger.finalize_log(success=True, forensic_success=False)
            return
        
        logger.log_and_print("✅ Linux 환경 확인 완료")
        
        # sudo 권한 확인 및 요청
        logger.log_and_print("🔐 sudo 권한 확인 중...")
        
        # 먼저 sudo 명령 사용 가능 여부 확인
        try:
            # sudo 명령 존재 여부 확인
            subprocess.run(['which', 'sudo'], capture_output=True, check=True, timeout=5)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            logger.log_and_print("❌ sudo 명령을 찾을 수 없습니다.")
            logger.log_and_print("포렌식 분석을 건너뜁니다.")
            logger.finalize_log(success=True, forensic_success=False)
            return
        
        # sudo 권한 확인 (비밀번호 없이 사용 가능한지)
        try:
            result = subprocess.run(['sudo', '-n', 'true'], capture_output=True, timeout=5)
            if result.returncode == 0:
                logger.log_and_print("✅ sudo 권한이 확인되었습니다. 포렌식 분석을 진행합니다.")
            else:
                # sudo 권한이 필요한 경우 사용자에게 안내
                logger.log_and_print("🔐 sudo 권한이 필요합니다.")
                logger.log_and_print("포렌식 분석을 계속하려면 sudo 비밀번호를 입력하세요.")
                
                # 사용자에게 계속할지 묻기
                try:
                    response = input("\n포렌식 분석을 계속하시겠습니까? (y/N): ").strip().lower()
                    if response in ['y', 'yes', '예']:
                        logger.log_and_print("✅ 포렌식 분석을 계속합니다...")
                        # sudo 권한 테스트
                        test_result = subprocess.run(['sudo', 'echo', 'sudo 권한 테스트 성공'], 
                                                  capture_output=True, text=True, timeout=10)
                        if test_result.returncode == 0:
                            logger.log_and_print("✅ sudo 권한이 정상적으로 작동합니다.")
                        else:
                            logger.log_and_print("❌ sudo 권한 테스트에 실패했습니다.")
                            logger.log_and_print("복호화는 완료되었으니 sudo 권한으로 별도 분석을 수행하세요.")
                            logger.finalize_log(success=True, forensic_success=False)
                            return
                    else:
                        logger.log_and_print("⚠️  포렌식 분석을 건너뜁니다.")
                        logger.log_and_print("복호화는 완료되었으니 sudo 권한으로 별도 분석을 수행하세요.")
                        logger.finalize_log(success=True, forensic_success=False)
                        return
                except (EOFError, KeyboardInterrupt):
                    logger.log_and_print("\n⚠️  사용자 입력이 중단되었습니다. 포렌식 분석을 건너뜁니다.")
                    logger.finalize_log(success=True, forensic_success=False)
                    return
                    
        except subprocess.TimeoutExpired:
            logger.log_and_print("⚠️  sudo 권한 확인이 타임아웃되었습니다.")
            logger.log_and_print("복호화는 완료되었으니 sudo 권한으로 별도 분석을 수행하세요.")
            logger.finalize_log(success=True, forensic_success=False)
            return
        except Exception as e:
            logger.log_and_print(f"⚠️  sudo 권한 확인 중 오류 발생: {e}")
            logger.log_and_print("복호화는 완료되었으니 sudo 권한으로 별도 분석을 수행하세요.")
            logger.finalize_log(success=True, forensic_success=False)
            return
        
        forensic_success = logger.run_forensic_analysis(decrypted_file)
        print("DEBUG: 5단계 완료")
        
        # 6. 최종 결과 정리
        print("DEBUG: 최종 정리")
        logger.finalize_log(success=True, forensic_success=forensic_success)
        
        if forensic_success:
            logger.log_and_print("\n🔍 추가 분석 권장사항:")
            logger.log_and_print("  - HTML 보고서를 브라우저에서 열어 시각적 분석 결과 확인")
            logger.log_and_print("  - 발견된 한글/이메일 데이터의 상세 내용 검토")
            logger.log_and_print("  - 휴대폰 본체 및 클라우드 동기화 데이터 추가 분석")
        else:
            logger.log_and_print("\n✅ FBE 복호화가 성공적으로 완료되었습니다!")
            logger.log_and_print("포렌식 분석은 Linux 환경에서 sudo 권한으로 별도 실행하세요.")
        
        print("DEBUG: 메인 함수 완료")
        
    except KeyboardInterrupt:
        print("\nDEBUG: 사용자 중단")
        logger.log_and_print("\n\n❌ 사용자에 의해 중단되었습니다.")
        logger.finalize_log(success=False, forensic_success=False)
        sys.exit(1)
    except Exception as e:
        print(f"\nDEBUG: 예상치 못한 오류: {e}")
        logger.log_and_print(f"\n❌ 예상치 못한 오류가 발생했습니다: {e}")
        import traceback
        traceback.print_exc()
        logger.finalize_log(success=False, forensic_success=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
