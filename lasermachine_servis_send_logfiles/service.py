import win32serviceutil
import win32service
import win32event
import socket
import os
import subprocess
import logging
import time

class PythonService(win32serviceutil.ServiceFramework):
    _svc_name_ = 'logfiles-send-lasermachine-service'
    _svc_display_name_ = 'LogFilesSend LaserMachine Service'
    _svc_description_ = 'Sends log files for the laser machine to the server.'

    def __init__(self, args):
        self.app_path = os.path.dirname(os.path.abspath(__file__))
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)
        self.is_running = True

        # Настройка логирования
        logging.basicConfig(
            filename=os.path.join(self.app_path, "service.log"),
            level=logging.DEBUG,
            format='[%(asctime)s] [%(levelname)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        logging.info("Служба инициализирована.")

    def SvcStop(self):
        logging.info("Остановка службы.")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_running = False

    def SvcDoRun(self):
        logging.info("Запуск службы.")
        self.main()

    def main(self):
        os.chdir(self.app_path)
        python_path = os.path.join(self.app_path, 'venv', 'Scripts', 'python.exe')
        command = f'{python_path} app.py'
        logging.info(f'Выполнение команды: {command}')
        
        try:
            process = subprocess.Popen(command, shell=True)
            while self.is_running:
                ret_code = process.poll()
                if ret_code is not None:
                    logging.error(f'Процесс завершился с кодом {ret_code}. Перезапуск через 60 секунд.')
                    time.sleep(60)
                    process = subprocess.Popen(command, shell=True)
                time.sleep(10)
        except Exception as e:
            logging.error(f'Ошибка в процессе выполнения: {str(e)}')
        finally:
            logging.info("Служба завершена.")
            self.ReportServiceStatus(win32service.SERVICE_STOPPED)

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(PythonService)
