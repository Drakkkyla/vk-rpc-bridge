import hashlib
import signal
import zipfile
import io
import json
import time
import sys
import os
import requests
import subprocess
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, \
    QSystemTrayIcon, QMenu, QMessageBox, QProgressBar, QListWidget, QHBoxLayout, QFrame, QListWidgetItem, QDialog, \
    QGraphicsDropShadowEffect, QLineEdit, QCheckBox, QGroupBox, QScrollArea, QSizePolicy
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, Qt, QThread, QPropertyAnimation, QSize, QPoint, QEasingCurve
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPainter, QLinearGradient, QBrush, QFont, QFontDatabase, QPalette, QPen
from pypresence import Presence, DiscordNotFound
from socketio import AsyncServer
from aiohttp import web, ClientSession
import asyncio
import threading
from packaging import version
import speech_recognition as sr

# Константы
DISCORD_CLIENT_ID = '1381313733845975261'
VERSION = "1.3.0"
GITHUB_REPO = "Drakkkyla/vk-rpc-bridge"
GITHUB_URL = f"https://github.com/{GITHUB_REPO}"
btns = [
    {"label": "Github", "url": "https://github.com/Drakkkyla/vk-rpc-bridge"},
    {"label": "VK", "url": "https://vk.com/draakylaaaa"}
]


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class ModernProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setFixedHeight(6)
        self.setMinimum(0)
        self.setMaximum(100)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Фон
        bg_rect = self.rect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(45, 45, 60))
        painter.drawRoundedRect(bg_rect, 3, 3)


class AnimatedButton(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.PointingHandCursor)
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.OutBack)

    def enterEvent(self, event):
        self.animation.stop()
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(self.geometry().adjusted(-5, -5, 5, 5))
        self.animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animation.stop()
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(self.geometry().adjusted(5, 5, -5, -5))
        self.animation.start()
        super().leaveEvent(event)


def create_shadow():
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(25)
    shadow.setColor(QColor(0, 0, 0, 180))
    shadow.setOffset(0, 5)
    return shadow


class GlassCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            GlassCard {
                background: rgba(30, 30, 47, 0.7);
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        self.setGraphicsEffect(create_shadow())


class UpdateManager(QThread):
    progress_signal = pyqtSignal(int)
    message_signal = pyqtSignal(str)
    complete_signal = pyqtSignal()
    download_complete = pyqtSignal()
    update_available = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.session = None
        self.download_task = None
        self.update_info = None
        self.cancelled = False

    async def check_updates_async(self):
        async with ClientSession() as session:
            async with session.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest") as resp:
                data = await resp.json()
                latest_version = data["tag_name"]
                if version.parse(latest_version) > version.parse(VERSION):
                    self.update_info = {
                        "version": latest_version,
                        "url": data["assets"][0]["browser_download_url"]
                    }
                    return True
        return False

    async def download_update_async(self):
        async with ClientSession() as session, session.get(self.update_info["url"]) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open("update.zip", "wb") as f:
                async for chunk in resp.content.iter_chunked(8192):
                    if self.cancelled:
                        raise Exception("Отменено")
                    f.write(chunk)
                    downloaded += len(chunk)
                    self.progress_signal.emit(int(100 * downloaded / total))
                    await asyncio.sleep(0.01)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if loop.run_until_complete(self.check_updates_async()):
                self.update_available.emit(self.update_info["version"], self.update_info["url"])
                self.message_signal.emit("Загрузка обновления...")
                loop.run_until_complete(self.download_update_async())
                if self.verify_checksum():
                    self.complete_signal.emit()
                else:
                    raise Exception("Ошибка проверки хеша")
            else:
                self.message_signal.emit("У вас актуальная версия!")
        except Exception as e:
            self.message_signal.emit(f"Ошибка: {str(e)}")
        finally:
            loop.close()



class UpdateDialog(QDialog):
    def __init__(self, parent, version, url):
        super().__init__(parent)
        self.setWindowTitle(f"Обновление до v{version}")
        self.setFixedSize(500, 300)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Основной контейнер
        self.container = GlassCard()
        layout = QVBoxLayout(self.container)

        # Заголовок
        header = QLabel(f"Доступна версия {version}")
        header_font = QFont("Arial", 16, QFont.Bold)
        header.setFont(header_font)
        header.setStyleSheet("color: #ECF0F1; margin: 15px 0;")
        header.setAlignment(Qt.AlignCenter)

        # Прогресс бар
        self.progress = ModernProgressBar()
        self.progress.setValue(0)

        # Текст статуса
        self.message = QLabel("Подготовка к загрузке...")
        self.message.setStyleSheet("color: #B0B0B0; margin: 10px 0;")
        self.message.setAlignment(Qt.AlignCenter)

        # Кнопки
        btn_layout = QHBoxLayout()
        self.cancel_btn = AnimatedButton("Отмена")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 65, 65, 0.8);
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 95, 95, 0.9);
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)

        self.install_btn = AnimatedButton("Установить")
        self.install_btn.setStyleSheet("""
            QPushButton {
                background: rgba(114, 137, 218, 0.8);
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(134, 157, 238, 0.9);
            }
        """)
        self.install_btn.clicked.connect(self.accept)
        self.install_btn.setEnabled(False)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.install_btn)
        btn_layout.addStretch()

        layout.addWidget(header)
        layout.addWidget(self.progress)
        layout.addWidget(self.message)
        layout.addLayout(btn_layout)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.container)

        self.update_manager = UpdateManager()
        self.update_manager.progress_signal.connect(self.progress.setValue)
        self.update_manager.message_signal.connect(self.message.setText)
        self.update_manager.complete_signal.connect(self.on_complete)
        self.update_manager.start()

    def on_complete(self):
        self.install_btn.setEnabled(True)
        self.message.setText("Обновление готово к установке!")

    def closeEvent(self, event):
        self.update_manager.cancelled = True
        super().closeEvent(event)


class BridgeSignals(QObject):
    log_signal = pyqtSignal(str, str)
    status_signal = pyqtSignal(str)
    update_rpc_signal = pyqtSignal(str, str)
    notification_signal = pyqtSignal(str, str, str)
    show_tray_message_signal = pyqtSignal(str, str)
    server_started = pyqtSignal()
    server_stopped = pyqtSignal()
    update_available = pyqtSignal(str, str)


    def __init__(self):
        super().__init__()
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.running = True




    def stop(self):
        self.running = False


class VKDiscordBridge(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VK Discord RPC Bridge")
        self.setGeometry(100, 100, 1000, 700)
        self.setMinimumSize(900, 600)
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0f0c29, stop:1 #302b63);
                color: #E0E0E0;
            }
        """)

        # Загрузка кастомных шрифтов
        self.load_fonts()

        # Системный трей
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(resource_path("icon.ico")))
        self.tray_menu = QMenu()
        self.tray_menu.setStyleSheet("""
            QMenu {
                background: #1E1E2F;
                color: #B0B0B0;
                border: 1px solid #3A3F45;
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 25px 8px 10px;
            }
            QMenu::item:selected {
                background: #7289DA;
                color: white;
                border-radius: 4px;
            }
        """)
        self.tray_menu.addAction("Открыть", self.show_normal)
        self.tray_menu.addAction("Настройки", self.show_settings)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction("Выйти", QApplication.quit)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.tray_activated)
        self.tray_icon.show()

        # Инициализация UI
        self.init_ui()
        self.signals = BridgeSignals()
        self.signals.log_signal.connect(self._log_message)
        self.signals.status_signal.connect(self.status_label.setText)
        self.signals.update_rpc_signal.connect(self._update_rpc)
        self.signals.show_tray_message_signal.connect(self.show_tray_message)
        self.signals.server_started.connect(self.on_server_started)
        self.signals.server_stopped.connect(self.on_server_stopped)
        self.signals.update_available.connect(self.show_update_dialog)

        # Остальная инициализация
        self.rpc = None
        self.server_running = False
        self.last_attempt_time = 0
        self.auto_reconnect = True
        self.current_song_data = None
        self.reconnect_timer = QTimer()
        self.reconnect_timer.timeout.connect(self.check_discord_connection)
        self.update_manager = UpdateManager()
        self.update_manager.message_signal.connect(self.log_message)
        self.update_manager.update_available.connect(self.signals.update_available.emit)
        QTimer.singleShot(3000, self.check_for_updates)

        # Для управления сервером
        self.server_thread = None
        self.loop = None
        self.runner = None
        self.site = None


    def load_fonts(self):
        font_dir = resource_path("fonts")
        if os.path.exists(font_dir):
            for font_file in os.listdir(font_dir):
                if font_file.endswith((".ttf", ".otf")):
                    QFontDatabase.addApplicationFont(os.path.join(font_dir, font_file))

    def init_ui(self):
        # Основной контейнер
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Верхняя панель
        top_bar = QWidget()
        top_bar.setFixedHeight(50)
        top_bar.setStyleSheet("background: rgba(30, 30, 47, 0.5);")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(15, 0, 15, 0)

        # Логотип и название
        logo_layout = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(resource_path("logo.png")).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title = QLabel("VK → Discord RPC")
        title_font = QFont("Montserrat", 14, QFont.Bold)
        title.setFont(title_font)
        title.setStyleSheet("color: #ECF0F1;")
        logo_layout.addWidget(logo)
        logo_layout.addWidget(title)
        logo_layout.setSpacing(10)

        # Кнопки управления окном
        btn_layout = QHBoxLayout()
        self.minimize_btn = QPushButton("—")
        self.minimize_btn.setFixedSize(30, 30)
        self.minimize_btn.setStyleSheet("""
            QPushButton {
                background: rgba(114, 137, 218, 0.3);
                color: white;
                border-radius: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(114, 137, 218, 0.5);
            }
        """)
        self.minimize_btn.clicked.connect(self.showMinimized)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 65, 65, 0.3);
                color: white;
                border-radius: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 65, 65, 0.5);
            }
        """)
        self.close_btn.clicked.connect(self.close)

        btn_layout.addWidget(self.minimize_btn)
        btn_layout.addWidget(self.close_btn)

        top_layout.addLayout(logo_layout)
        top_layout.addStretch()
        top_layout.addLayout(btn_layout)

        main_layout.addWidget(top_bar)

        # Основное содержимое
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)

        # Левая панель - Плеер
        player_card = GlassCard()
        player_layout = QVBoxLayout(player_card)
        player_layout.setContentsMargins(20, 20, 20, 20)
        player_layout.setSpacing(15)

        player_title = QLabel("Сейчас играет")
        player_title_font = QFont("Montserrat", 12, QFont.Bold)
        player_title.setFont(player_title_font)
        player_title.setStyleSheet("color: #ECF0F1;")

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(250, 250)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a2a6c, stop:1 #b21f1f);
                border-radius: 15px;
            }
        """)

        # Анимация обложки
        self.cover_animation = QPropertyAnimation(self.cover_label, b"geometry")
        self.cover_animation.setDuration(1000)
        self.cover_animation.setEasingCurve(QEasingCurve.OutBack)

        self.track_info = QLabel("Нет активного трека")
        self.track_info.setStyleSheet("color: #FFFFFF; font-size: 16px;")
        self.track_info.setAlignment(Qt.AlignCenter)
        self.track_info.setWordWrap(True)

        self.progress = ModernProgressBar()
        self.progress.setValue(50)

        player_layout.addWidget(player_title, alignment=Qt.AlignCenter)
        player_layout.addWidget(self.cover_label, alignment=Qt.AlignCenter)
        player_layout.addWidget(self.track_info)
        player_layout.addWidget(self.progress)

        # Правая панель - Логи и управление
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(20)

        # Панель управления
        control_card = GlassCard()
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(20, 20, 20, 20)

        control_title = QLabel("Управление")
        control_title.setFont(player_title_font)
        control_title.setStyleSheet("color: #ECF0F1; margin-bottom: 15px;")
        control_title.setAlignment(Qt.AlignCenter)



        # Кнопки управления
        btn_row1 = QHBoxLayout()
        self.start_btn = AnimatedButton(" Запустить сервер")
        self.start_btn.setIcon(QIcon(resource_path("play.svg")))
        self.start_btn.setIconSize(QSize(24, 24))
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: rgba(114, 137, 218, 0.8);
                color: white;
                border-radius: 10px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(134, 157, 238, 0.9);
            }
        """)
        self.start_btn.setToolTip("Запустить сервер")

        self.stop_btn = AnimatedButton(" Остановить сервер")
        self.stop_btn.setIcon(QIcon(resource_path("stop.svg")))
        self.stop_btn.setIconSize(QSize(24, 24))
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 65, 65, 0.8);
                color: white;
                border-radius: 10px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 95, 95, 0.9);
            }
        """)
        self.stop_btn.setToolTip("Остановить сервер")
        self.stop_btn.setEnabled(False)

        btn_row1.addWidget(self.start_btn)
        btn_row1.addWidget(self.stop_btn)

        btn_row2 = QHBoxLayout()
        self.reconnect_btn = AnimatedButton(" Переподключить RPC")
        self.reconnect_btn.setIcon(QIcon(resource_path("refresh.svg")))
        self.reconnect_btn.setIconSize(QSize(24, 24))
        self.reconnect_btn.setStyleSheet("""
            QPushButton {
                background: rgba(46, 204, 113, 0.8);
                color: white;
                border-radius: 10px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(56, 224, 133, 0.9);
            }
        """)

        self.settings_btn = AnimatedButton(" Настройки")
        self.settings_btn.setIcon(QIcon(resource_path("settings.svg")))
        self.settings_btn.setIconSize(QSize(24, 24))
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background: rgba(155, 89, 182, 0.8);
                color: white;
                border-radius: 10px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(175, 109, 202, 0.9);
            }
        """)

        btn_row2.addWidget(self.reconnect_btn)
        btn_row2.addWidget(self.settings_btn)

        control_layout.addWidget(control_title)
        control_layout.addLayout(btn_row1)
        control_layout.addLayout(btn_row2)

        # Панель логов
        log_card = GlassCard()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(15, 15, 15, 15)

        log_title = QLabel("Журнал событий")
        log_title.setFont(player_title_font)
        log_title.setStyleSheet("color: #ECF0F1; margin-bottom: 10px;")

        self.log = QListWidget()
        self.log.setStyleSheet("""
            QListWidget {
                background: rgba(30, 30, 47, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                color: #B0B0B0;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QListWidget::item:last {
                border-bottom: none;
            }
        """)
        self.log.setMinimumHeight(200)

        log_layout.addWidget(log_title)
        log_layout.addWidget(self.log)

        right_layout.addWidget(control_card)
        right_layout.addWidget(log_card)

        content_layout.addWidget(player_card, 6)
        content_layout.addWidget(right_panel, 4)

        main_layout.addWidget(content_widget)

        # Статус бар
        status_bar = QWidget()
        status_bar.setFixedHeight(30)
        status_bar.setStyleSheet("background: rgba(30, 30, 47, 0.5);")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(15, 0, 15, 0)

        self.status_label = QLabel("Статус: Не активно")
        self.status_label.setStyleSheet("color: #B0B0B0;")

        version_label = QLabel(f"Версия: {VERSION}")
        version_label.setStyleSheet("color: #7289DA;")

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(version_label)

        self.start_btn.clicked.connect(self.start_server)
        self.stop_btn.clicked.connect(self.stop_server)
        self.reconnect_btn.clicked.connect(self.check_discord_connection)
        self.settings_btn.clicked.connect(self.show_settings)


        main_layout.addWidget(status_bar)




    def show_normal(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.activateWindow()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal()

    def check_for_updates(self):
        self.update_manager.start()

    def show_update_dialog(self, version, url):
        dialog = UpdateDialog(self, version, url)
        if dialog.exec_() == QDialog.Accepted:
            self.install_update()

    def install_update(self):
        try:
            # Распаковка обновления
            with zipfile.ZipFile("update.zip", 'r') as zip_ref:
                zip_ref.extractall(".")

            # Запуск нового экземпляра приложения
            subprocess.Popen([sys.executable, *sys.argv])
            QApplication.quit()
        except Exception as e:
            self.log_message(f"Ошибка установки обновления: {str(e)}", "ERROR")
            QMessageBox.critical(self, "Ошибка", f"Не удалось установить обновление: {str(e)}")

    def show_tray_message(self, title, message):
        self.tray_icon.showMessage(title, message, QIcon(resource_path("update_icon.png")), 5000)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage("VK RPC Bridge", "Приложение свернуто в трей", QIcon(resource_path("icon.ico")),
                                   2000)

    def check_discord_connection(self):
        if not self.rpc:
            try:
                self.rpc = Presence(DISCORD_CLIENT_ID)
                self.rpc.connect()
                self.log_message("Подключение к Discord RPC", "RPC")
                self.reconnect_btn.setEnabled(True)
            except DiscordNotFound:
                self.rpc = None
                self.log_message("Discord не найден", "WARNING")
            except Exception as e:
                self.rpc = None
                self.log_message(f"Ошибка подключения: {str(e)}", "ERROR")

    async def handle_song_change(self, sid, data):
        self.log_message(f"Получены данные: {data}", "RECV")
        try:
            if 'artist' in data and 'songName' in data:
                self.current_song_data = data.copy()
            if 'paused' in data and not ('artist' in data and 'songName' in data) and self.current_song_data:
                data = self.current_song_data.copy()
                data['paused'] = data.get('paused', False)
            artist = data.get('artist')
            song_name = data.get('songName')
            album = data.get('album')
            duration = data.get('duration', 0)
            position = data.get('position', 0)
            paused = data.get('paused', False)
            if not artist or not song_name:
                self.log_message("Неполные данные о треке", "WARNING")
                self.signals.update_rpc_signal.emit(json.dumps({}), "")
                return
            track_data = {
                "artist": artist,
                "title": song_name,
                "album": album,
                "duration": duration,
                "position": position,
                "paused": paused
            }
            self.signals.update_rpc_signal.emit(json.dumps(track_data), "")
        except Exception as e:
            self.log_message(f"Ошибка обработки трека: {str(e)}", "ERROR")

    def _update_rpc(self, json_data, _):
        try:
            data = json.loads(json_data)
            artist = data.get("artist", "")
            title = data.get("title", "")
            album = data.get("album", "")
            duration = data.get("duration", 0)
            position = data.get("position", 0)
            paused = data.get("paused", False)
            current_time = time.time()
            if not self.rpc:
                if self.auto_reconnect and (current_time - self.last_attempt_time) > 10:
                    self.last_attempt_time = current_time
                    self.check_discord_connection()
                return
            activity = {
                "activity_type": 2,
                "details": artist,
                "state": title,
                "buttons": btns,
                "large_image": "embedded_cover",
                "large_text": "VK Music",
                "small_image": "vk_logo",
                "small_text": "Слушает в VK"
            }
            if paused:
                activity["small_image"] = "pause_icon"
                activity["small_text"] = "Пауза"
            if duration > 0 and position >= 0:
                activity["timestamps"] = {
                    "start": int(current_time - position),
                    "end": int(current_time - position + duration)
                }
            if artist and title:
                self.rpc.update(**activity)
                status_text = f"{artist} - {title} {'(пауза)' if paused else ''}"
                self.status_label.setText(f"Статус: {status_text}")
                self.log_message(f"RPC обновлен: {status_text}", "SUCCESS")
                self.track_info.setText(f"<b>{title}</b><br>{artist}<br>{album}")
                self.progress.setValue(int(position / duration * 100) if duration > 0 else 0)

                # Анимация обложки
                self.cover_animation.stop()
                self.cover_animation.setStartValue(self.cover_label.geometry())
                self.cover_animation.setEndValue(self.cover_label.geometry().adjusted(-10, -10, 10, 10))
                self.cover_animation.finished.connect(
                    lambda: self.cover_animation.setEndValue(self.cover_label.geometry().adjusted(10, 10, -10, -10))
                )
                self.cover_animation.start()
            else:
                self.rpc.clear()
                self.status_label.setText("Статус: Не активно")
                self.log_message("RPC статус очищен", "INFO")
        except DiscordNotFound:
            self.log_message("Discord не найден! Переподключитесь", "ERROR")
            self.rpc = None
        except Exception as e:
            self.log_message(f"RPC ошибка: {str(e)}", "ERROR")
            self.rpc = None

    def start_server(self):
        if self.server_running:
            self.log_message("Сервер уже запущен", "WARNING")
            return
        self.start_btn.setEnabled(False)
        self.log_message("Запуск сервера...", "SERVER")
        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()

    def run_server(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            sio = AsyncServer(async_mode='aiohttp', cors_allowed_origins='*', engineio_logger=False,
                              allow_upgrades=True, ping_timeout=20, max_http_buffer_size=1e8)
            app = web.Application()
            sio.attach(app)

            @sio.on('song_changed')
            async def on_song_changed(sid, data):
                await self.handle_song_change(sid, data)

            @sio.on('song_paused')
            async def on_song_paused(sid, data):
                await self.handle_song_change(sid, {'paused': True})

            runner = web.AppRunner(app)
            self.loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, port=8112)
            self.loop.run_until_complete(site.start())
            self.server_running = True
            self.signals.server_started.emit()
            self.log_message("Сервер запущен на порту 8112", "SUCCESS")
            self.loop.run_forever()
        except Exception as e:
            self.log_message(f"Ошибка сервера: {str(e)}", "ERROR")
            self.server_running = False
            self.signals.server_stopped.emit()

    def stop_server(self):
        if not self.server_running:
            return
        self.log_message("Остановка сервера...", "SERVER")
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.log_message("Цикл событий остановлен", "INFO")
        self.server_running = False
        self.signals.server_stopped.emit()

    def on_server_started(self):
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("Статус: Сервер запущен")

    def on_server_stopped(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Статус: Сервер остановлен")

    def _log_message(self, message, level="INFO"):
        color = {
            "INFO": "#66b3ff",
            "SUCCESS": "#4CAF50",
            "WARNING": "#FFA500",
            "ERROR": "#ff4444",
            "RPC": "#9c27b0",
            "SERVER": "#FF9800",
            "RECV": "#9C27B0"
        }.get(level, "#ffffff")
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        item = QListWidgetItem(f"[{timestamp}] [{level}] {message}")
        item.setForeground(QColor(color))

        # Добавляем иконку в зависимости от уровня
        icon_map = {
            "INFO": "info.svg",
            "SUCCESS": "success.svg",
            "WARNING": "warning.svg",
            "ERROR": "error.svg",
            "RPC": "rpc.svg",
            "SERVER": "server.svg",
            "RECV": "receive.svg"
        }
        if level in icon_map:
            item.setIcon(QIcon(resource_path(icon_map[level])))

        self.log.addItem(item)
        self.log.scrollToBottom()

    def log_message(self, message, level="INFO"):
        self.signals.log_signal.emit(message, level)

    def show_settings(self):
        # Реализация окна настроек
        settings_dialog = QDialog(self)
        settings_dialog.setWindowTitle("Настройки")
        settings_dialog.setFixedSize(500, 400)
        settings_dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0f0c29, stop:1 #302b63);
                color: #E0E0E0;
                border-radius: 15px;
            }
        """)

        layout = QVBoxLayout()

        # Группа настроек RPC
        rpc_group = QGroupBox("Настройки Discord RPC")
        rpc_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #7289DA;
                border: 1px solid #7289DA;
                border-radius: 10px;
                margin-top: 20px;
                padding-top: 10px;
            }
        """)
        rpc_layout = QVBoxLayout()

        auto_reconnect = QCheckBox("Автоматическое переподключение к Discord")
        auto_reconnect.setChecked(self.auto_reconnect)
        auto_reconnect.stateChanged.connect(lambda state: setattr(self, 'auto_reconnect', bool(state)))

        show_notifications = QCheckBox("Показывать уведомления о треках")
        show_notifications.setChecked(True)

        rpc_layout.addWidget(auto_reconnect)
        rpc_layout.addWidget(show_notifications)
        rpc_group.setLayout(rpc_layout)

        # Группа настроек сервера
        server_group = QGroupBox("Настройки сервера")
        server_group.setStyleSheet(rpc_group.styleSheet())
        server_layout = QVBoxLayout()

        port_input = QLineEdit("8112")
        port_input.setStyleSheet("""
            QLineEdit {
                background: rgba(30, 30, 47, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 8px;
                color: #ECF0F1;
            }
        """)

        server_layout.addWidget(QLabel("Порт сервера:"))
        server_layout.addWidget(port_input)
        server_group.setLayout(server_layout)

        layout.addWidget(rpc_group)
        layout.addWidget(server_group)
        layout.addStretch()

        # Кнопки
        btn_layout = QHBoxLayout()
        save_btn = AnimatedButton("Сохранить")
        save_btn.setStyleSheet("""
            QPushButton {
                background: rgba(114, 137, 218, 0.8);
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(134, 157, 238, 0.9);
            }
        """)
        save_btn.clicked.connect(settings_dialog.accept)

        cancel_btn = AnimatedButton("Отмена")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 65, 65, 0.8);
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 95, 95, 0.9);
            }
        """)
        cancel_btn.clicked.connect(settings_dialog.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)
        settings_dialog.setLayout(layout)
        settings_dialog.exec_()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")

    # Установка глобальных стилей
    app.setStyleSheet("""
        QToolTip {
            background-color: #1E1E2F;
            color: #ECF0F1;
            border: 1px solid #7289DA;
            border-radius: 5px;
            padding: 5px;
        }
    """)

    window = VKDiscordBridge()
    window.show()
    window.reconnect_timer.start(10000)
    sys.exit(app.exec_())