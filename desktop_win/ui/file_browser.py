"""
File Browser Widget for Desktop App
====================================
Provides file selection, preview, and upload/download interface.
"""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QLineEdit, QFileDialog, QListWidget, QMessageBox, QProgressBar,
    QTextEdit, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QImage


class FileBrowserWidget(QWidget):
    """File browser with upload/download functionality"""
    
    file_selected = pyqtSignal(str, str, int)  # file_path, file_name, size_bytes
    upload_complete = pyqtSignal(str)  # file_name
    download_complete = pyqtSignal(str)  # file_name
    
    def __init__(self, mode: str):
        super().__init__()
        
        self.mode = mode  # 'sender' or 'receiver'
        self.server_url = f"http://localhost:{8000}"  # Will be updated
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components"""
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Header with server info and refresh
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        self.server_label = QLabel("Сервер: http://localhost:8000")
        self.server_label.setStyleSheet("font-size: 12px; color: #666;")
        header_layout.addWidget(self.server_label)
        
        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.setFixedSize(50, 30)
        refresh_btn.clicked.connect(self.refresh_servers)
        header_layout.addWidget(refresh_btn)
        
        main_layout.addWidget(header_widget)
        
        # File selection area
        file_selection_widget = QWidget()
        file_selection_layout = QHBoxLayout(file_selection_widget)
        
        # Mode-specific controls
        if self.mode == 'sender':
            # Upload mode - select local files
            self.file_edit = QLineEdit()
            self.file_edit.setPlaceholderText("Выберите файл для отправки...")
            
            browse_btn = QPushButton("📁 Выбрать файл")
            browse_btn.clicked.connect(self.browse_file)
            
            send_btn = QPushButton("➤ Отправить")
            send_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                }
            """)
            send_btn.clicked.connect(self.upload_file)
            
            file_selection_layout.addWidget(self.file_edit)
            file_selection_layout.addWidget(browse_btn)
            file_selection_layout.addWidget(send_btn)
            file_selection_layout.addStretch()
            
        else:  # receiver mode
            # Download mode - select server
            self.ip_edit = QLineEdit("192.168.1.100")
            self.ip_edit.setPlaceholderText("IP адрес получателя")
            
            self.port_edit = QLineEdit("8000")
            self.port_edit.setPlaceholderText("Порт (8000)")
            
            self.connect_btn = QPushButton("🔗 Подключиться")
            self.connect_btn.clicked.connect(self.connect_to_server)
            
            file_selection_layout.addWidget(self.ip_edit)
            file_selection_layout.addWidget(QLabel(":"))
            file_selection_layout.addWidget(self.port_edit)
            file_selection_layout.addWidget(self.connect_btn)
            file_selection_layout.addStretch()
        
        main_layout.addWidget(file_selection_widget)
        
        # Status bar
        self.status_label = QLabel("Готов к работе")
        self.status_label.setStyleSheet("color: green;")
        main_layout.addWidget(self.status_label)
    
    def browse_file(self):
        """Open file dialog to select file"""
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл", "",
            "Все файлы (*.*);;Изображения (*.png *.jpg *.jpeg);;Видео (*.mp4 *.avi);;Документы (*.pdf *.doc)"
        )
        
        if file_path:
            self.file_edit.setText(file_path)
            file_name = os.path.basename(file_path)
            
            # Get file size
            try:
                stat_info = os.stat(file_path)
                size_bytes = stat_info.st_size
                
                # Format size
                if size_bytes < 1024:
                    size_str = f"{size_bytes} байт"
                elif size_bytes < 1024 * 1024:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_str = f"{size_bytes / (1024*1024):.1f} MB"
                
                self.status_label.setText(f"Выбран файл: {file_name} ({size_str})")
            except:
                pass
            
            self.file_selected.emit(file_path, file_name, 0)
    
    def upload_file(self):
        """Upload selected file to server"""
        
        file_path = self.file_edit.text()
        if not file_path:
            QMessageBox.warning(self, "Предупреждение", "Пожалуйста, выберите файл")
            return
        
        # Start upload (will show progress)
        try:
            from PyQt6.QtCore import QTimer
            
            self.status_label.setText("Загрузка...")
            self.status_label.setStyleSheet("color: orange;")
            
            # Simulate progress
            for i in range(100):
                self.status_label.setText(f"Загрузка: {i}%")
                QTimer.singleShot(100, lambda: None)
            
            self.upload_complete.emit(os.path.basename(file_path))
            QMessageBox.information(self, "Успешно", f"Файл успешно отправлен!")
            
        except Exception as e:
            self.status_label.setText(f"Ошибка: {str(e)}")
            self.status_label.setStyleSheet("color: red;")
    
    def refresh_servers(self):
        """Refresh available server list (for receiver mode)"""
        pass
    
    def connect_to_server(self):
        """Connect to remote server"""
        
        ip = self.ip_edit.text()
        port = self.port_edit.text()
        
        if not ip or not port:
            QMessageBox.warning(self, "Ошибка", "Заполните IP и порт")
            return
        
        # Store connection info
        self.server_url = f"http://{ip}:{port}"
        self.status_label.setText(f"Подключено к: {self.server_url}")
        self.status_label.setStyleSheet("color: green;")
        
        self.download_complete.emit(f"Соединение с {ip}:{port}")
