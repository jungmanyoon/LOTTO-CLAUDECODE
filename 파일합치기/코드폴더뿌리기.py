import os
from tkinter import Tk, filedialog, messagebox
import chardet

def read_file_with_fallback(filename):
    with open(filename, 'rb') as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        encoding = result['encoding']
    
    try:
        with open(filename, 'r', encoding=encoding) as file:
            return file.read(), encoding
    except UnicodeDecodeError:
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                return file.read(), 'utf-8'
        except UnicodeDecodeError:
            with open(filename, 'r', encoding='latin1') as file:
                return file.read(), 'latin1'

def save_module_files(combined_content, main_folder, encoding='utf-8'):
    modules = combined_content.split('\n# ')
    for module in modules:
        if not module.strip():
            continue

        # Extract the first line as the path comment and the rest as the content
        lines = module.split('\n')
        path_comment = lines[0].strip()
        if path_comment.startswith('src'):
            relative_path = path_comment.replace("\\", "/")
            file_content = '\n'.join(lines[1:])
            
            module_path = os.path.join(main_folder, relative_path)
            module_folder = os.path.dirname(module_path)

            # Create the folder if it does not exist
            if not os.path.exists(module_folder):
                os.makedirs(module_folder)

            # Write the content to the file with the detected encoding
            with open(module_path, 'w', encoding=encoding, newline='\n') as file:
                file.write(file_content)

def select_main_folder_and_save():
    root = Tk()
    root.withdraw()
    
    # Select the merged Python file
    merged_file = filedialog.askopenfilename(
        title="합쳐진 파이썬 파일 선택",
        filetypes=[("Python files", "*.py")]
    )
    
    if not merged_file:
        messagebox.showerror("오류", "합쳐진 파이썬 파일을 선택해야 합니다.")
        return

    combined_content, encoding = read_file_with_fallback(merged_file)

    # Select the main folder to save the modules
    main_folder = filedialog.askdirectory(title="메인 모듈 폴더 선택")

    if not main_folder:
        messagebox.showerror("오류", "메인 모듈 폴더를 선택해야 합니다.")
        return

    # Save module files in the main folder with detected encoding
    save_module_files(combined_content, main_folder, encoding)
    messagebox.showinfo("완료", "모듈 파일들이 성공적으로 저장되었습니다.")

def main():
    root = Tk()
    root.withdraw()
    select_main_folder_and_save()

if __name__ == "__main__":
    main()