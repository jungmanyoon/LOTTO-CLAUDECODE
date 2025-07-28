import os
from tkinter import Tk, messagebox
import chardet
import pyperclip
import re

# 파일 인코딩 감지 및 파일 읽기 함수
def read_file_with_fallback(filename):
    with open(filename, 'rb') as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        encoding = result['encoding']
    
    try:
        with open(filename, 'r', encoding=encoding, newline='') as file:
            return file.read(), encoding
    except UnicodeDecodeError:
        try:
            with open(filename, 'r', encoding='utf-8', newline='') as file:
                return file.read(), 'utf-8'
        except UnicodeDecodeError:
            with open(filename, 'r', encoding='latin1', newline='') as file:
                return file.read(), 'latin1'

# 파일 내용에 파일 경로를 주석으로 추가하는 함수
def add_filename_comment(filename, base_path):
    content, encoding = read_file_with_fallback(filename)
    
    relative_path = os.path.relpath(filename, base_path)
    basename_comment = f"# {relative_path}\n"
    
    path_comment_re = re.compile(r'^# .*/.*\.(py|yaml|env|txt)\n', re.MULTILINE)
    
    lines = content.split('\n')
    if lines[0].startswith('#') and path_comment_re.match(lines[0] + '\n'):
        lines[0] = basename_comment.strip()
        content = '\n'.join(lines)
    else:
        content = basename_comment + content
    
    return content

# 결합 파일을 생성하되, 2000줄을 넘지 않도록 분할 저장하는 함수
def combine_files(files, base_path, output_basename="병합_코드분리", output_dir=None):
    combined_content = ""
    current_line_count = 0
    file_index = 1
    encodings = {}
    additional_text = "\n\"나머지 코드를 다음대화 때 더 알려줄테니 지금 준 코드를 간단하게 분석해줘 이어서 다음 코드를 계속 알려줄께\"\n"

    for i, file in enumerate(files):
        module_content = add_filename_comment(file, base_path)
        module_lines = module_content.splitlines()

        if current_line_count + len(module_lines) > 2000:
            # 추가 텍스트를 현재 파일에만 추가
            combined_content += additional_text
            output_file = os.path.join(output_dir, f"{output_basename}_{file_index}.py")
            save_combined_content(combined_content, output_file)
            file_index += 1
            combined_content = ""
            current_line_count = 0

        combined_content += module_content + "\n"
        current_line_count += len(module_lines)
        _, encoding = read_file_with_fallback(file)
        encodings[file] = encoding

    if combined_content:
        output_file = os.path.join(output_dir, f"{output_basename}_{file_index}.py")
        # 마지막 파일에는 추가 문구를 생략
        if file_index == 1 or i == len(files) - 1:  # 첫 파일이자 마지막 파일이거나, 마지막 파일이면
            save_combined_content(combined_content, output_file)
        else:
            combined_content += additional_text
            save_combined_content(combined_content, output_file)

    return encodings

# 결합된 내용을 파일에 저장하고, 클립보드에 복사하는 함수
def save_combined_content(combined_content, output_file):
    with open(output_file, 'w', encoding='utf-8', newline='\n') as file:
        file.write(combined_content)
    pyperclip.copy(combined_content)
    print(f"결합된 내용이 {output_file}에 저장되었습니다.")
    print("결합된 내용이 클립보드에 복사되었습니다.")

# 사용자로부터 파일 결합 작업을 실행할 것인지 확인받고, 결합 작업을 수행하는 함수
def select_and_combine_files():
    root = Tk()
    root.withdraw()

    current_dir = os.path.realpath(os.path.dirname(__file__))
    parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))
    exclude_dir = os.path.join(parent_dir, '파일합치기')

    all_files = []
    for root_dir, _, files in os.walk(parent_dir):
        real_root_dir = os.path.realpath(root_dir)
        if real_root_dir.startswith(exclude_dir):
            continue
        for file in files:
            if file.endswith(('.py', '.yaml', '.env', 'requirements.txt')):
                all_files.append(os.path.join(real_root_dir, file))

    if all_files:
        encodings = combine_files(all_files, parent_dir, output_dir=current_dir)
        for file, encoding in encodings.items():
            print(f"{file} encoded with {encoding}")

# 메인 함수
def main():
    root = Tk()
    root.withdraw()
    choice = messagebox.askyesno("파일 결합", "상위 폴더 내의 모든 파일을 결합하시겠습니까?")

    if choice:
        select_and_combine_files()

if __name__ == "__main__":
    main()
