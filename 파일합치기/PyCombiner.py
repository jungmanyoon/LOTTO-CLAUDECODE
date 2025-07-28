import os
from tkinter import Tk, messagebox
import chardet
import pyperclip
import re

# 주어진 파일의 내용을 읽어오되, 파일 인코딩에 따라 적절한 방식으로 읽어오는 함수
def read_file_with_fallback(filename):
    # 파일을 바이너리 모드로 열어 인코딩을 감지
    with open(filename, 'rb') as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        encoding = result['encoding']
    
    # 감지된 인코딩으로 파일을 읽음
    try: 
        with open(filename, 'r', encoding=encoding, newline='') as file:
            return file.read(), encoding
    except UnicodeDecodeError:
        # 만약 감지된 인코딩으로 읽지 못하면, UTF-8로 시도
        try:
            with open(filename, 'r', encoding='utf-8', newline='') as file:
                return file.read(), 'utf-8'
        except UnicodeDecodeError:
            # UTF-8로도 실패하면, Latin1로 읽기 시도
            with open(filename, 'r', encoding='latin1', newline='') as file:
                return file.read(), 'latin1'

# 파일 내용에 파일 경로를 주석으로 추가하는 함수
def add_filename_comment(filename, base_path):
    content, encoding = read_file_with_fallback(filename)
    
    # 파일의 상대 경로를 계산하여 주석 형태로 만듦
    relative_path = os.path.relpath(filename, base_path)
    basename_comment = f"# {relative_path}\n"
    
    # 기존의 파일 경로 주석을 찾기 위한 정규 표현식
    path_comment_re = re.compile(r'^# .*/.*\.(py|yaml|env|txt)\n', re.MULTILINE)
    
    # 파일 내용을 줄 단위로 나눔
    lines = content.split('\n')
    # 첫 번째 줄이 주석이고, 기존 주석이 경로 주석이라면 이를 새 주석으로 교체
    if lines[0].startswith('#') and path_comment_re.match(lines[0] + '\n'):
        lines[0] = basename_comment.strip()
        content = '\n'.join(lines)
    else:
        # 기존 경로 주석이 없다면 새 주석을 파일 내용 앞에 추가
        content = basename_comment + content
    
    return content

# 주어진 파일들을 결합하여 하나의 파일로 만드는 함수
def combine_files(files, output_file, base_path):
    combined_content = ""
    encodings = {}
    for file in files:
        module_content = add_filename_comment(file, base_path)
        combined_content += module_content + "\n"
        _, encoding = read_file_with_fallback(file)
        encodings[file] = encoding

    # 결합된 내용을 UTF-8로 저장
    with open(output_file, 'w', encoding='utf-8', newline='\n') as file:
        file.write(combined_content)
    return combined_content, encodings

# 사용자로부터 파일 결합 작업을 실행할 것인지 확인받고, 결합 작업을 수행하는 함수
def select_and_combine_files():
    root = Tk()
    root.withdraw()

    # 현재 스크립트의 경로와 상위 폴더 경로를 계산
    current_dir = os.path.realpath(os.path.dirname(__file__))
    parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))
    exclude_dir = os.path.join(parent_dir, '파일합치기')

    all_files = []
    for root_dir, _, files in os.walk(parent_dir):
        real_root_dir = os.path.realpath(root_dir)
        # 특정 폴더를 제외하고 파일 리스트 작성
        if real_root_dir.startswith(exclude_dir):
            continue
        for file in files:
            if file.endswith(('.py', '.yaml', '.env', 'requirements.txt')):
                all_files.append(os.path.join(real_root_dir, file))

    if all_files:
        output_file = os.path.join(current_dir, "Merged_Code.py")
        combined_content, encodings = combine_files(all_files, output_file, parent_dir)
        pyperclip.copy(combined_content)
        print(f"결합된 내용이 {output_file}에 저장되었습니다.")
        print("결합된 내용이 클립보드에 복사되었습니다.")
        for file, encoding in encodings.items():
            print(f"{file} encoded with {encoding}")

# 스크립트의 메인 함수로, 파일 결합을 할 것인지 사용자에게 묻고 실행
def main():
    root = Tk()
    root.withdraw()
    choice = messagebox.askyesno("파일 결합", "상위 폴더 내의 모든 파일을 결합하시겠습니까?")

    if choice:
        select_and_combine_files()

if __name__ == "__main__":
    main()
