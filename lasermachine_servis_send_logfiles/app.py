import os
import glob
import hashlib
import requests
import json
from flask import Flask
from flask_apscheduler import APScheduler
import time
import threading
import logging

logging.basicConfig(filename='app.log', level=logging.DEBUG)
logging.info('Starting Flask app')


app = Flask(__name__)

class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Определение полного пути к файлу settings.conf
config_path = os.path.join(os.path.dirname(__file__), 'settings.conf')

def load_config(config_path):
    
    """Загружает конфигурацию из указанного файла."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as file:
        return json.loads(file.read())

# Загрузка настроек из файла settings.conf
config = load_config(config_path)
folder_path = config['folder_path']
temp_dir = config['temp_dir']
server_url = config['server_url']
search_period_days = config['search_period_days']
port = config['port']
interval = config['interval']
laser_id = config['laser_id']
log_lock = threading.Lock()

# Полные пути к файлам сохранения
last_file_hashes_path = os.path.join(temp_dir, 'last_file_hashes.txt')
last_lines_saved_path = os.path.join(temp_dir, 'last_lines_saved.txt')

def calculate_file_hash(file_path):
    """Вычисляет хэш-сумму файла."""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(8192)
            while chunk:
                hasher.update(chunk)
                chunk = f.read(8192)
        return hasher.hexdigest()
    except Exception as e:
        print(f"Ошибка при вычислении хэша файла: {e}")
        return None

def find_recent_rtf_files(folder_path):
    """Находит все файлы с расширением .rtf в указанной папке за последние N дней."""
    rtf_files = glob.glob(os.path.join(folder_path, "*.rtf"))
    recent_files = []
    current_time = time.time()
    for file_path in rtf_files:
        file_mod_time = os.path.getmtime(file_path)
        # Проверяем, были ли файлы изменены за последние N дней
        if (current_time - file_mod_time) <= (search_period_days * 86400):  # 86400 секунд в сутках
            recent_files.append(file_path)
    return recent_files

def read_file_content(file_path):
    """Читает содержимое файла."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Ошибка при чтении файла {file_path}: {e}")
        return ""

def read_new_lines(file_path, last_lines):
    """Читает новые строки из файла."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            new_lines = lines[last_lines:]
            return ''.join(new_lines), len(lines)
    except Exception as e:
        print(f"Ошибка при чтении новых строк из файла {file_path}: {e}")
        return "", 0

def write_content_to_file(file_path, content):
    """Записывает содержимое в файл."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"Ошибка при записи файла {file_path}: {e}")

def send_file_to_server(file_path, server_url, laser_id):
    """Отправляет файл на сервер с дополнительным параметром laser_id."""
    try:
        print(f"Отправляем файл: {file_path} на сервер: {server_url} с laser_id: {laser_id}")
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            data = {'laser_id': laser_id}  # Добавляем номер станка в данные запроса
            response = requests.post(server_url, files=files, data=data)
            print(f"Отправка файла завершена. Код статуса: {response.status_code}")
            print(f"Ответ сервера: {response.text}")
            return response
    except Exception as e:
        print(f"Ошибка при отправке файла: {e}")
        return None


def get_saved_file_hashes():
    """Получает хэши всех ранее обработанных файлов из файла сохранения."""
    if os.path.exists(last_file_hashes_path):
        with open(last_file_hashes_path, 'r') as f:
            return {line.strip().split(',')[0]: line.strip().split(',')[1] for line in f}
        
    return {}

def save_file_hashes(file_hashes):
    """Сохраняет хэши всех обработанных файлов в файл."""
    try:
        with open(last_file_hashes_path, 'w') as f:
            for file_path, file_hash in file_hashes.items():
                f.write(f"{file_path},{file_hash}\n")
    except Exception as e:
        print(f"Ошибка при сохранении хэшей файлов: {e}")

def get_saved_last_lines():
    """Получает количество строк в каждом файле из файла сохранения."""
    if os.path.exists(last_lines_saved_path):
        with open(last_lines_saved_path, 'r') as f:
            return {line.strip().split(',')[0]: int(line.strip().split(',')[1]) for line in f}
    return {}

def save_last_lines(file_lines):
    """Сохраняет количество строк в каждом файле в файл."""
    try:
        with open(last_lines_saved_path, 'w') as f:
            for file_path, lines in file_lines.items():
                f.write(f"{file_path},{lines}\n")
    except Exception as e:
        print(f"Ошибка при сохранении количества строк: {e}")

def check_and_send_file():
    """Находит все новые файлы и изменения в ранее обработанных файлах, отправляет их на сервер."""
    rtf_files = find_recent_rtf_files(folder_path) 
    if not rtf_files:
        print("Файлы с расширением .rtf не найдены.")
        return

    saved_hashes = get_saved_file_hashes()
    saved_lines = get_saved_last_lines()
    new_file_hashes = {}
    new_file_lines = {}
    
    # Проверяем и отправляем новые строки в последнем обработанном файле
    for file_path in saved_lines:
        if file_path in rtf_files:
            new_content, new_line_count = read_new_lines(file_path, saved_lines[file_path])
            if new_content:
                temp_file_path = os.path.join(temp_dir, f"temp_{os.path.basename(file_path)}")
                write_content_to_file(temp_file_path, new_content)
                response = send_file_to_server(temp_file_path, server_url, laser_id)
                if response and response.status_code == 200:
                    new_file_hashes[file_path] = calculate_file_hash(file_path)
                    new_file_lines[file_path] = new_line_count
                os.remove(temp_file_path)

    # Проверяем и отправляем новые файлы
    for file_path in rtf_files:
        if file_path not in saved_hashes:
            # Новый файл
            temp_file_path = os.path.join(temp_dir, f"temp_{os.path.basename(file_path)}")
            original_content = read_file_content(file_path)
            write_content_to_file(temp_file_path, original_content)
            response = send_file_to_server(temp_file_path, server_url, laser_id)
            if response and response.status_code == 200:
                new_file_hashes[file_path] = calculate_file_hash(file_path)
                new_file_lines[file_path] = len(read_file_content(file_path).splitlines())
                os.remove(temp_file_path)

    # Сохраняем новые хэши и количество строк файлов после успешной отправки
    if new_file_hashes:
        saved_hashes.update(new_file_hashes)
        save_file_hashes(saved_hashes)
    if new_file_lines:
        saved_lines.update(new_file_lines)
        save_last_lines(saved_lines)

# Добавляем задачу в планировщик
scheduler.add_job(id='check_and_send_file', func=check_and_send_file, trigger='interval', seconds=interval)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False, threaded=True)
    
