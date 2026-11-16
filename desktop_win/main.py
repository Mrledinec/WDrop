"""Windows entry point for the local file transfer application."""

import argparse
from hashlib import sha256
import json
import logging
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from tempfile import TemporaryFile

import qrcode
import ifaddr
import uvicorn
from PyQt6.QtCore import (
    QEvent, QFile, QLocale, QSettings, QSignalBlocker, QStandardPaths, Qt, QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton,
    QStyle, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from zeroconf import IPVersion, ServiceInfo, Zeroconf

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from desktop_win.server.server_api import TransferService, local_ipv4, make_api
from desktop_win.update import APP_NAME, VERSION, check_release, download_installer


STATE_LABELS = {
    "pending": "Ожидает ответа",
    "accepted": "Принят",
    "transferring": "Передаётся",
    "completed": "Завершён",
    "rejected": "Отклонён",
    "expired": "Время ожидания истекло",
    "failed": "Ошибка",
}


def file_size(size):
    return QLocale.system().formattedDataSize(size, 2, QLocale.DataSizeFormat.DataSizeTraditionalFormat)


class Window(QMainWindow):
    prepared = pyqtSignal(str)
    update_checked = pyqtSignal(object, str)
    installer_downloaded = pyqtSignal(object, str)

    def __init__(self, service, server, address, bind="0.0.0.0", fixed_address=False):
        super().__init__()
        self.service = service
        self.server = server
        self.last_peers = None
        self.last_peer_rows = None
        self.last_offers = None
        self.last_history = None
        self.zeroconf = None
        self.mdns_service = None
        self.broadcast_address = None
        self.broadcast_ready = False
        self.bind = bind
        self.preferred_address = address
        self.fixed_address = fixed_address
        self.interfaces = []
        self.prepared.connect(self.show_status)
        self.update_checked.connect(self.show_update_result)
        self.installer_downloaded.connect(self.show_installer)
        self.update_dir = Path(service.db_path).parent
        self.settings = QSettings(str(self.update_dir / "desktop.ini"), QSettings.Format.IniFormat)
        self.update_busy = False
        self.update_dialog = None
        self.release = None
        self.exiting = False
        self.tray = None

        self.setWindowTitle(APP_NAME)
        settings_menu = self.menuBar().addMenu("Настройки")
        settings_menu.addAction("Папка для полученных файлов…", self.choose_inbox)
        settings_menu.addAction("Очистить историю передач…", self.clear_history)
        settings_menu.addSeparator()
        settings_menu.addAction("Проверить обновление", self.open_updates)
        self.resize(900, 740)
        self.setAcceptDrops(True)
        self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon))
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        form = QFormLayout()
        self.address = QComboBox()
        self.address.currentIndexChanged.connect(self.select_network)
        form.addRow("Локальная сеть", self.address)
        layout.addLayout(form)

        row = QHBoxLayout()
        row.addWidget(self.button("Подключить телефон", self.invite))
        row.addWidget(self.button("Лимит приёма", self.change_limit))
        row.addStretch()
        layout.addLayout(row)
        self.pairing_status = QLabel()
        self.pairing_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.pairing_status)

        self.pair_buttons = QWidget()
        pair_controls = QHBoxLayout(self.pair_buttons)
        pair_controls.setContentsMargins(0, 0, 0, 0)
        pair_controls.addWidget(self.button("Подтвердить подключение", lambda: self.service.reply_pairing(True)))
        pair_controls.addWidget(self.button("Отклонить подключение", lambda: self.service.reply_pairing(False)))
        pair_controls.addStretch()
        self.pair_buttons.hide()
        layout.addWidget(self.pair_buttons)

        layout.addWidget(self.section_label("Устройства"))
        self.devices = self.table(("Имя устройства", "Автоприём от устройства", "Статус"))
        self.devices.setMaximumHeight(135)
        self.devices.itemChanged.connect(self.change_trust)
        layout.addWidget(self.devices)
        row = QHBoxLayout()
        row.addWidget(self.button("Отправить файл", self.send_file))
        row.addWidget(self.button("Переименовать", self.rename_peer))
        row.addStretch()
        row.addWidget(self.button("Удалить устройство", self.remove_peer))
        layout.addLayout(row)

        self.drop_area = QLabel("Перетащите файлы сюда для отправки")
        self.drop_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_area.setMinimumHeight(55)
        self.drop_area.setStyleSheet(
            "border: 1px dashed palette(mid); border-radius: 8px; background: palette(alternate-base);"
        )
        layout.addWidget(self.drop_area)
        layout.addWidget(self.section_label("Передачи"))
        self.transfers = self.table(("Файл", "Направление", "Устройство", "Состояние", "Прогресс"))
        layout.addWidget(self.transfers)
        row = QHBoxLayout()
        row.addWidget(self.button("Принять", lambda: self.decide(True)))
        row.addWidget(self.button("Отклонить", lambda: self.decide(False)))
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(self.section_label("История"))
        self.history = self.table(("Файл", "Направление", "Размер"))
        self.history.setMaximumHeight(150)
        self.history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self.history_menu)
        self.history.cellDoubleClicked.connect(self.open_history_file)
        layout.addWidget(self.history)
        self.show_status(f"Папка приёма: {service.inbox}")

        self.invite_panel = None
        self.setup_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(500)
        self.network_timer = QTimer(self)
        self.network_timer.timeout.connect(self.refresh_network)
        self.network_timer.start(3000)
        self.refresh_network()
        self.refresh()

    @staticmethod
    def section_label(title):
        label = QLabel(title)
        font = label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        label.setFont(font)
        return label

    @staticmethod
    def table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        return table

    @staticmethod
    def button(label, function):
        button = QPushButton(label)
        button.clicked.connect(function)
        return button

    @staticmethod
    def selected(table):
        rows = table.selectionModel().selectedRows()
        cell = table.item(rows[0].row(), 0) if rows else None
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def set_rows(self, table, rows, checkbox_column=None):
        selected = self.selected(table)
        with QSignalBlocker(table):
            table.setRowCount(len(rows))
            table.clearSelection()
            for row_index, (key, *columns) in enumerate(rows):
                for column_index, value in enumerate(columns):
                    cell = QTableWidgetItem(str(value))
                    cell.setData(Qt.ItemDataRole.UserRole, key)
                    if column_index == checkbox_column:
                        cell.setText("Автоматически" if value else "С подтверждением")
                        cell.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                                      | Qt.ItemFlag.ItemIsUserCheckable)
                        cell.setCheckState(Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
                    table.setItem(row_index, column_index, cell)
                if key == selected:
                    table.selectRow(row_index)

    def show_status(self, message):
        self.statusBar().showMessage(message)

    def choose_inbox(self):
        directory = QFileDialog.getExistingDirectory(self, "Папка для полученных файлов", str(self.service.inbox))
        if not directory:
            return
        path = Path(directory)
        try:
            with TemporaryFile(dir=path):
                pass
        except OSError as error:
            QMessageBox.warning(self, "Папка приёма", f"Не удалось записать файл в эту папку.\n{error}")
            return
        with self.service.lock:
            self.service.inbox = path
        self.settings.setValue("transfer/inbox", str(path))
        self.show_status(f"Папка приёма: {path}")

    def confirm(self, title, message):
        return QMessageBox.question(
            self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def clear_history(self):
        if self.confirm("Очистить историю", "Удалить все записи о передачах? Файлы останутся на диске."):
            self.edit_history(self.service.history.clear_transfer_history)

    def edit_history(self, operation):
        try:
            operation()
        except Exception as error:
            QMessageBox.warning(self, "История передач", str(error))
        self.refresh()

    def history_item(self, row):
        cell = self.history.item(row, 0)
        if cell is None:
            return None
        record_id = cell.data(Qt.ItemDataRole.UserRole)
        return next((item for item in self.last_history if item.id == record_id), None)

    def open_history_file(self, row, _column):
        if item := self.history_item(row):
            self.open_file(Path(item.file_path))

    def open_file(self, path, reveal=False):
        try:
            if not path.is_file():
                raise FileNotFoundError("Файл перемещён или удалён.")
            if reveal:
                subprocess.Popen(["explorer.exe", "/select,", str(path)])
            else:
                os.startfile(str(path))
        except OSError as error:
            QMessageBox.warning(self, "Открыть файл", str(error))

    def history_menu(self, position):
        row = self.history.indexAt(position).row()
        item = self.history_item(row)
        if item is None:
            return
        self.history.selectRow(row)
        path = Path(item.file_path)
        menu = QMenu(self.history)
        open_file = menu.addAction("Открыть файл")
        reveal = menu.addAction("Открыть расположение файла")
        delete_file = None
        if item.source_device_id != self.service.pin:
            delete_file = menu.addAction("Удалить файл в корзину…")
            delete_file.setEnabled(path.is_file())
        menu.addSeparator()
        remove = menu.addAction("Удалить из списка")
        action = menu.exec(self.history.viewport().mapToGlobal(position))
        if action is None:
            return
        if action == open_file or action == reveal:
            self.open_file(path, reveal=action == reveal)
        elif action == delete_file:
            if self.confirm("Удалить файл", f"Переместить «{path.name}» в корзину?"):
                target = QFile(str(path))
                if not target.moveToTrash():
                    QMessageBox.warning(self, "Удаление файла", target.errorString())
                    return
                self.edit_history(lambda: self.service.history.delete_transfer_record(item.id))
        elif action == remove:
            self.edit_history(lambda: self.service.history.delete_transfer_record(item.id))

    def open_updates(self):
        if self.update_dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Обновления")
            dialog.setMinimumSize(400, 200)
            dialog.resize(560, 260)
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel(f"Текущая версия: {VERSION}"))
            self.update_status = QPlainTextEdit()
            self.update_status.setReadOnly(True)
            layout.addWidget(self.update_status)
            actions = QHBoxLayout()
            self.check_update_button = self.button("Проверить обновление", self.check_updates)
            self.install_update_button = self.button("Установить", self.install_update)
            self.install_update_button.hide()
            actions.addWidget(self.check_update_button)
            actions.addWidget(self.install_update_button)
            actions.addStretch()
            layout.addLayout(actions)
            self.update_dialog = dialog
        self.update_dialog.show()
        self.update_dialog.raise_()
        self.update_dialog.activateWindow()
        self.check_updates()

    def check_updates(self):
        if self.update_busy:
            return
        self.release = None
        self.start_update_task(check_release, self.update_checked, "Проверяем обновления…")

    def install_update(self):
        if self.update_busy or self.release is None:
            return
        release = self.release
        self.start_update_task(
            lambda: download_installer(release, self.update_dir / "updates"),
            self.installer_downloaded, "Скачиваем установщик…",
        )

    def set_update_state(self, status, busy=False):
        self.update_busy = busy
        self.update_status.setPlainText(status)
        self.check_update_button.setEnabled(not busy)
        self.install_update_button.setVisible(self.release is not None)
        self.install_update_button.setEnabled(not busy)

    def start_update_task(self, operation, signal, status):
        self.set_update_state(status, busy=True)

        def run():
            try:
                signal.emit(operation(), "")
            except Exception as error:
                signal.emit(None, str(error))

        threading.Thread(target=run, daemon=True, name="Windows update").start()

    def show_update_result(self, release, error):
        self.release = release
        if error:
            self.set_update_state(error)
        elif release is None:
            self.set_update_state("Установлена актуальная версия.")
        else:
            self.set_update_state(f"Доступна версия {release.version}.")

    def show_installer(self, path, error):
        if error:
            self.set_update_state(error)
            return
        self.set_update_state("Установщик скачан и проверен.")
        if QMessageBox.question(
            self.update_dialog, "Запустить установщик",
            "Приложение закроется, текущие передачи прервутся. Продолжить установку?",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            os.startfile(str(path))
        except OSError as error:
            self.set_update_state(f"Не удалось открыть установщик. {error}")
        else:
            self.quit_from_tray()

    def refresh(self):
        with self.service.lock:
            self.service.prune()
            pending = self.service.pairing
            peers = self.service.peers()
            names = {peer_id: name for peer_id, name, _ in peers}
            peer_rows = [
                (peer_id, name, trusted, "В сети" if self.service.has_recent_contact(peer_id) else "Не в сети")
                for peer_id, name, trusted in peers
            ]
            offers = [
                (offer.id, offer.metadata.name, "На ПК" if offer.direction == "upload" else "На телефон",
                 names.get(offer.peer_id, "Удалённое устройство"), self.state_label(offer),
                 self.transfer_progress(offer))
                for offer in reversed(list(self.service.offers.values()))
            ]
        if pending is not None:
            self.pairing_status.setText(f"Подключение запрашивает: {pending.name}")
            self.pair_buttons.show()
            if self.invite_panel:
                self.invite_panel.close()
        elif self.pair_buttons.isVisible():
            self.pairing_status.clear()
            self.pair_buttons.hide()

        self.last_peers = peers
        if peer_rows != self.last_peer_rows:
            self.last_peer_rows = peer_rows
            self.set_rows(self.devices, peer_rows, checkbox_column=1)
        if offers != self.last_offers:
            self.last_offers = offers
            self.set_rows(self.transfers, [(*row[:-1], "") for row in offers])
            for index, (*_, progress) in enumerate(offers):
                if progress is None:
                    self.transfers.removeCellWidget(index, 4)
                    continue
                percent, transferred, total = progress
                bar = QProgressBar()
                bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                bar.setValue(percent)
                bar.setFormat("%p%")
                bar.setToolTip(f"{file_size(transferred)} / {file_size(total)}")
                self.transfers.setCellWidget(index, 4, bar)

        history = self.service.history.get_transfer_history()
        if history != self.last_history:
            self.last_history = history
            self.set_rows(self.history, [
                (item.id, item.filename, "На телефон" if item.source_device_id == self.service.pin else "На ПК",
                 file_size(item.file_size))
                for item in history
            ])

    @staticmethod
    def state_label(offer):
        label = STATE_LABELS[offer.state]
        if offer.state == "pending":
            return f"{label} · {offer.payload()['seconds_left']} с"
        return label

    @staticmethod
    def transfer_progress(offer):
        if offer.state != "transferring":
            return None
        size = offer.metadata.size
        received = min(size, offer.received)
        return (received * 100 // size if size else 100, received, size)

    def refresh_network(self):
        interfaces = sorted(
            (adapter.name, adapter.nice_name, ip.ip)
            for adapter in ifaddr.get_adapters() for ip in adapter.ips
            if isinstance(ip.ip, str) and 0 < ip.network_prefix < 32
            and not ip.ip.startswith(("127.", "169.254."))
            and self.bind in {"0.0.0.0", ip.ip}
        )
        if self.bind != "0.0.0.0" and not interfaces:
            interfaces = [(self.bind, "Сетевой интерфейс", self.bind)]
        if interfaces != self.interfaces or self.address.count() == 0:
            previous = self.address.currentData()
            saved = self.settings.value("network/interface", "", str) if self.bind == "0.0.0.0" else ""
            device = saved or (previous[0] if previous else "")
            preferred = self.preferred_address if self.fixed_address else local_ipv4()
            self.interfaces = interfaces
            with QSignalBlocker(self.address):
                self.address.clear()
                for key, name, ip in interfaces:
                    self.address.addItem(f"{name} · {ip}", (key, ip))
                selected = next((
                    index for index, (key, _, ip) in enumerate(interfaces)
                    if (key, ip) == previous and (not saved or key == saved)
                ), None)
                if selected is None and device:
                    selected = next((
                        index for index, (key, _, _) in enumerate(interfaces) if key == device
                    ), None)
                if selected is None and (saved or not interfaces):
                    selected = self.address.count()
                    self.address.addItem("Выбранная сеть недоступна" if saved else "Локальная сеть недоступна")
                if selected is None:
                    selected = next((
                        index for index, (_, _, ip) in enumerate(interfaces) if ip == preferred
                    ), 0)
                self.address.setCurrentIndex(selected)
        current = self.address.currentData()
        self.advertise(current[1] if current else "")

    def select_network(self):
        current = self.address.currentData()
        if current:
            self.settings.setValue("network/interface", current[0])
        self.interfaces = []
        self.refresh_network()

    def advertise(self, address):
        addresses = (address,) if address and not address.startswith("127.") else ()
        ready = self.service.pairing_available()
        if self.broadcast_address == addresses and self.broadcast_ready == ready:
            return
        self.stop_advertising()
        if not addresses or address.startswith("127."):
            return
        service_type = "_localtransfer._tcp.local."
        hostname = f"transfer-{self.service.pin[:12]}.local."
        try:
            data = ServiceInfo(
                service_type,
                f"Transfer-{self.service.pin[:12]}{'-pair' if ready else ''}.{service_type}",
                addresses=[socket.inet_aton(ip) for ip in addresses],
                port=self.service.port,
                properties={"id": self.service.pin, "name": self.service.name, "ready": "1" if ready else "0"},
                server=hostname,
            )
            self.zeroconf = Zeroconf(interfaces=list(addresses), ip_version=IPVersion.V4Only)
            self.zeroconf.register_service(data)
            self.mdns_service = data
            self.broadcast_address = addresses
            self.broadcast_ready = ready
        except (OSError, ValueError) as error:
            self.stop_advertising()
            self.show_status(f"Автообнаружение недоступно. Подключение по QR работает. {error}")

    def stop_advertising(self):
        if self.zeroconf:
            if self.mdns_service:
                self.zeroconf.unregister_service(self.mdns_service)
            self.zeroconf.close()
        self.zeroconf = self.mdns_service = self.broadcast_address = None

    def invite(self):
        network = self.address.currentData()
        if not network:
            self.show_status("Подключитесь к локальной сети")
            return
        address = network[1]
        if self.invite_panel:
            self.invite_panel.close()
        code = json.dumps(self.service.new_invite(address), ensure_ascii=True, separators=(",", ":"))
        self.advertise(address)
        panel = QWidget(self, Qt.WindowType.Dialog)
        panel.setWindowTitle("Подключить телефон")
        box = QVBoxLayout(panel)
        box.addWidget(QLabel("Отсканируйте QR в приложении на телефоне. Код действует 2 минуты."))
        manual = self.service.manual_invite
        manual_label = QLabel(f"Код для поиска в сети: {manual}")
        manual_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(manual_label)
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
        qr.add_data(code)
        qr.make(fit=True)
        modules = qr.get_matrix()
        image = QImage(len(modules), len(modules), QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        black = QColor("black")
        for y, line in enumerate(modules):
            for x, dark in enumerate(line):
                if dark:
                    image.setPixelColor(x, y, black)
        preview = QLabel()
        qr_size = len(modules) * 5
        preview.setPixmap(QPixmap.fromImage(image).scaled(qr_size, qr_size))
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(preview)
        box.addWidget(self.button("Скопировать приглашение", lambda: QApplication.clipboard().setText(code)))
        panel.show()
        self.invite_panel = panel

    def change_limit(self):
        current = self.service.limit
        value, ok = QInputDialog.getInt(
            self, "Лимит приёма",
            "Максимальный размер файла в МиБ (0 — без ограничения):",
            current // 1024**2 if current is not None else 0,
            0, 1_048_576,
        )
        if ok:
            self.service.set_limit(value * 1024**2 if value else None)
            self.show_status(f"Лимит: {value} МиБ" if value else "Лимит размера отключён")

    def change_trust(self, cell):
        if cell.column() != 1:
            return
        peer_id = cell.data(Qt.ItemDataRole.UserRole)
        self.service.trust(peer_id, cell.checkState() == Qt.CheckState.Checked)
        QTimer.singleShot(0, self.refresh)

    def rename_peer(self):
        peer_id = self.selected(self.devices)
        peer = next((peer for peer in self.last_peers or [] if peer[0] == peer_id), None)
        if peer is None:
            self.show_status("Выберите устройство для переименования")
            return
        name, ok = QInputDialog.getText(self, "Переименовать устройство", "Имя в списке", text=peer[1])
        if ok:
            try:
                self.service.rename(peer_id, name)
            except ValueError as error:
                self.show_status(str(error))
            self.refresh()

    def remove_peer(self):
        if peer_id := self.selected(self.devices):
            answer = QMessageBox.question(self, "Удалить устройство", "Отозвать доступ этого устройства?")
            if answer == QMessageBox.StandardButton.Yes:
                try:
                    self.service.revoke(peer_id)
                except ValueError as error:
                    self.show_status(str(error))
                self.refresh()

    def send_file(self):
        peer_id = self.receiver()
        if not peer_id:
            self.show_status("Сначала выберите устройство в списке")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Выберите файлы для отправки")
        if not paths:
            return
        self.queue_files(peer_id, [Path(path) for path in paths])

    def receiver(self):
        selected = self.selected(self.devices)
        peers = self.last_peers or []
        return selected or (peers[0][0] if len(peers) == 1 else None)

    def dragEnterEvent(self, event):
        if any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        files = [path for path in paths if path.is_file()]
        if not files:
            self.show_status("Перетащите один или несколько файлов")
            return
        peer_id = self.receiver()
        if not peer_id:
            self.show_status("Выберите устройство и перетащите файлы снова")
            return
        event.acceptProposedAction()
        self.queue_files(peer_id, files)

    def queue_files(self, peer_id, paths):
        self.show_status("Подготовка файлов…")

        def prepare():
            queued = 0
            errors = []
            for path in paths:
                try:
                    self.service.queue_file(peer_id, path)
                    queued += 1
                except Exception as error:
                    errors.append(f"{path.name} · {getattr(error, 'detail', error)}")
            status = f"Предложений отправлено: {queued} из {len(paths)}"
            if errors:
                status += f". {errors[0]}"
            self.prepared.emit(status)

        threading.Thread(target=prepare, daemon=True, name="Prepare upload").start()

    def decide(self, accept):
        if offer_id := self.selected(self.transfers):
            try:
                self.service.decide(offer_id, accept, "upload")
            except Exception as error:
                self.show_status(f"Передача: {getattr(error, 'detail', error)}")
            self.refresh()

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_menu = QMenu(self)
        self.tray_menu.addAction("Открыть", self.restore_window)
        self.tray_menu.addAction("Выход", self.quit_from_tray)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(self.windowTitle())
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()

    def tray_activated(self, reason):
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.restore_window()

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_from_tray(self):
        self.exiting = True
        self.close()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.tray and self.isMinimized():
            QTimer.singleShot(0, self.hide_if_minimized)

    def hide_if_minimized(self):
        if self.isMinimized():
            self.hide()

    def closeEvent(self, event):
        if self.tray and not self.exiting:
            if self.invite_panel:
                self.invite_panel.close()
            event.ignore()
            self.hide()
            return
        if self.tray:
            self.tray.hide()
        self.timer.stop()
        self.network_timer.stop()
        self.stop_advertising()
        self.server.should_exit = True
        super().closeEvent(event)


def activate_instance(name):
    connection = QLocalSocket()
    connection.connectToServer(name)
    if not connection.waitForConnected(250):
        return False
    connection.disconnectFromServer()
    return True


def run_app(args, windowed):
    identity = f"{os.path.normcase(str(args.data_dir.resolve()))}:{args.port}"
    instance_name = "LocalTransfer-" + sha256(identity.encode()).hexdigest()[:24]
    if args.port and activate_instance(instance_name):
        return 0

    with socket.socket() as listener:
        try:
            listener.bind((args.bind, args.port))
        except OSError as error:
            if args.port and activate_instance(instance_name):
                return 0
            raise RuntimeError(f"Не удалось открыть порт {args.port}: {error}") from error

        settings = QSettings(str(args.data_dir / "desktop.ini"), QSettings.Format.IniFormat)
        saved_inbox = settings.value("transfer/inbox", "", str)
        default_inbox = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
                             or Path.home() / "Downloads") / "Local Transfer"
        saved_path = Path(saved_inbox) if saved_inbox else None
        inbox = args.inbox or (saved_path if saved_path and saved_path.is_dir() else default_inbox)
        service = TransferService(args.data_dir, inbox.resolve(), listener.getsockname()[1])
        if windowed:
            logging.basicConfig(
                filename=args.data_dir / "windows.log", encoding="utf-8",
                format="%(asctime)s %(levelname)s %(message)s",
            )
        server = uvicorn.Server(uvicorn.Config(
            make_api(service), ssl_certfile=str(service.cert), ssl_keyfile=str(service.key),
            log_level="warning", access_log=False,
            log_config=None if windowed else uvicorn.config.LOGGING_CONFIG,
        ))
        address = args.address or local_ipv4()
        window = Window(service, server, address, bind=args.bind, fixed_address=bool(args.address))
        if args.inbox is None and saved_path and not saved_path.is_dir():
            window.show_status(f"Выбранная папка недоступна. Папка приёма: {service.inbox}")
        instance = QLocalServer()
        instance.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)

        def show_existing_window():
            while instance.hasPendingConnections():
                connection = instance.nextPendingConnection()
                connection.disconnectFromServer()
                connection.deleteLater()
            window.restore_window()

        if args.port:
            instance.newConnection.connect(show_existing_window)
            if not instance.listen(instance_name):
                logging.warning("Cannot register window activation: %s", instance.errorString())
        worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True, name="Local HTTPS")
        worker.start()
        try:
            window.show()
            return QApplication.instance().exec()
        finally:
            instance.close()
            server.should_exit = True
            worker.join(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=f"{APP_NAME} — обмен файлами по локальной сети")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--bind", default="0.0.0.0", help="IPv4-интерфейс для локального сервера")
    parser.add_argument("--address", help="IPv4-адрес ПК, который будет указан в QR")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LocalTransfer")
    parser.add_argument("--inbox", type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    windowed = sys.stdout is None or sys.stderr is None
    try:
        return run_app(args, windowed)
    except Exception as error:
        if not windowed:
            raise
        logging.exception("Application startup failed")
        QMessageBox.critical(None, f"Не удалось запустить {APP_NAME}", str(error))
        return 1


if __name__ == "__main__":
    sys.exit(main())

