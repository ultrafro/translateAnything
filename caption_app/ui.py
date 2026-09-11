import json
import time
import html
import sys
import threading
from collections import OrderedDict
from PySide6.QtCore import Qt, QObject, Signal, QTimer, QPoint, QEvent
from PySide6.QtGui import QFont, QColor, QPainter
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QComboBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QSpinBox, QProgressBar, QCheckBox, QMessageBox, QLayout, QTextBrowser, QDoubleSpinBox)
from .config import ROOT, LANGUAGES
from .audio import Capture, devices, microphones
from .engine import Engine


class Events(QObject):
    update = Signal(str)
    status = Signal(str)
    caption = Signal(object, str, object, bool)
    ready = Signal()
    level = Signal(int)
    mic_level = Signal(int)


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.layout = QVBoxLayout(self)
        self.layout.setSizeConstraint(QLayout.SetNoConstraint)
        self.layout.setContentsMargins(16, 12, 16, 12)
        self.font_size = 18
        self.screen_index = 0
        self.user_position = None
        self.drag_offset = None
        self.collapsed = False
        self.history = OrderedDict()
        self.follow_live = True
        self.updating_scroll = False
        self.rendered_content = None
        header = QHBoxLayout()
        title = QLabel('CONVERSATION TRANSCRIPT')
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        title.setToolTip('Drag this bar to move the transcript')
        title.setStyleSheet('color: #91a6bd; font: 11px "Segoe UI"; background: transparent;')
        header.addWidget(title, 1)
        self.follow_button = QPushButton('● Following live')
        self.follow_button.setToolTip('Follow the newest captions')
        self.follow_button.setStyleSheet('color: #72e5ba; background: #243245; border: 0; border-radius: 5px; padding: 5px;')
        self.follow_button.clicked.connect(self.resume_live)
        header.addWidget(self.follow_button)
        self.minimize_button = QPushButton('—')
        self.minimize_button.setToolTip('Minimize transcript')
        self.minimize_button.setFixedWidth(30)
        self.minimize_button.setStyleSheet('color: #aec4d8; background: #243245; border: 0; border-radius: 5px; padding: 5px;')
        self.minimize_button.clicked.connect(self.toggle_minimized)
        header.addWidget(self.minimize_button)
        clear = QPushButton('Clear')
        clear.setStyleSheet('color: #aec4d8; background: #243245; border: 0; border-radius: 5px; padding: 5px 12px;')
        clear.clicked.connect(self.clear_history)
        header.addWidget(clear)
        self.layout.addLayout(header)
        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.installEventFilter(self)
        self.transcript.viewport().installEventFilter(self)
        self.transcript.verticalScrollBar().valueChanged.connect(self.on_scroll_changed)
        self.transcript.setStyleSheet('''
            QTextBrowser { color: white; background: transparent; border: 0; }
            QScrollBar:vertical { background: #15202e; width: 9px; }
            QScrollBar::handle:vertical { background: #536579; min-height: 24px; border-radius: 4px; }
        ''')
        self.layout.addWidget(self.transcript, 1)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.render)
        self.scroll_timer = QTimer(self)
        self.scroll_timer.setInterval(16)
        self.scroll_timer.timeout.connect(self.scroll_to_bottom)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(9, 14, 24, 225))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 16, 16)

    def display(self, original, translations):
        self.update_caption((-1, 1, 1), original, translations, True)
        self.render()

    def update_caption(self, identity, original, translations, final):
        key = tuple(identity[:2])
        revision = identity[2] if len(identity) > 2 else 0
        if key not in self.history:
            self.history[key] = {'time': time.strftime('%H:%M:%S'), 'original': '',
                                 'translations': {}, 'source_revision': -1, 'translation_revision': -1,
                                 'source_final': False, 'ready': False}
        entry = self.history[key]
        if revision >= entry['source_revision']:
            entry['original'] = original
            entry['source_revision'] = revision
            entry['source_final'] = final
            if not translations:
                entry['ready'] = False
        if translations and revision >= entry['translation_revision']:
            entry['translations'] = dict(translations)
            entry['translation_revision'] = revision
            entry['ready'] = final and revision >= entry['source_revision']
        while len(self.history) > 50:
            self.history.popitem(last=False)
        if not self.render_timer.isActive():
            self.render_timer.start(60)
        self.place()
        self.show()

    def clear_history(self):
        self.history.clear()
        self.follow_live = True
        self.update_follow_button()
        self.render()

    def entry_positions(self):
        document = self.transcript.document()
        positions = {}
        block = document.begin()
        while block.isValid():
            fragment = block.begin()
            while not fragment.atEnd():
                for name in fragment.fragment().charFormat().anchorNames():
                    positions[name] = document.documentLayout().blockBoundingRect(block).top()
                fragment += 1
            block = block.next()
        return positions

    def render(self):
        self.render_timer.stop()
        bar = self.transcript.verticalScrollBar()
        previous = bar.value()
        positions = self.entry_positions()
        anchor = next((name for name, y in reversed(list(positions.items())) if y <= previous), None)
        offset = previous - positions[anchor] if anchor else 0
        sections = []
        for key, entry in self.history.items():
            state = '✓ Ready' if entry['ready'] else 'Translating…' if entry['source_final'] else 'Listening…'
            state_color = '#72e5ba' if entry['ready'] else '#d6b875'
            text_color = '#ffffff' if entry['ready'] else '#96a5b8'
            lines = [f'<p style="color:#8da5bd; font-size:10pt; margin-bottom:5px;"><a name="entry_{key[0]}_{key[1]}">{entry["time"]}</a>'
                     f' &nbsp; <span style="color:{state_color};">{state}</span></p>']
            translations = entry['translations']
            if not translations:
                translations = {'live': entry['original']}
            for code, text in translations.items():
                direction = 'rtl' if code == 'ar' else 'ltr'
                label = LANGUAGES.get(code, 'Live')
                lines.append(f'<p dir="{direction}" style="color:{text_color}; margin-top:3px; margin-bottom:8px;">'
                             f'<span style="color:#84d7c6; font-size:11pt;">{label}</span><br>'
                             f'{html.escape(text)}</p>')
            sections.append(''.join(lines))
        content = '<hr style="color:#304052;">'.join(sections)
        if not content:
            content = '<p style="color:#91a6bd;">Waiting for speech…</p>'
        content += '<p style="font-size:8pt; margin-top:8px;">&nbsp;</p>'
        signature = (content, self.font_size)
        if signature == self.rendered_content:
            return
        first_render = self.rendered_content is None
        self.updating_scroll = True
        self.transcript.setUpdatesEnabled(False)
        try:
            self.transcript.setFont(QFont('Segoe UI', self.font_size))
            self.transcript.setHtml(content)
            positions = self.entry_positions()
            if anchor:
                # Keep the same entry at the same screen height, even when older
                # translations reflow or the oldest retained entry is removed.
                previous = round(positions[anchor] + offset) if anchor in positions else 0
            bar.setValue(bar.maximum() if first_render and self.follow_live else min(previous, bar.maximum()))
            self.rendered_content = signature
        finally:
            self.transcript.setUpdatesEnabled(True)
            self.updating_scroll = False
        if self.follow_live:
            self.scroll_timer.start()

    def on_scroll_changed(self, value):
        if not self.updating_scroll:
            bar = self.transcript.verticalScrollBar()
            self.follow_live = bar.maximum() - value <= 8
            if not self.follow_live:
                self.scroll_timer.stop()
            self.update_follow_button()

    def update_follow_button(self):
        self.follow_button.setText('● Following live' if self.follow_live else '↓ Resume live')

    def eventFilter(self, watched, event):
        scrolling_up = (event.type() == QEvent.Wheel and
                        (event.angleDelta().y() > 0 or event.pixelDelta().y() > 0))
        scrolling_up |= (event.type() == QEvent.KeyPress and
                         event.key() in (Qt.Key_Up, Qt.Key_PageUp, Qt.Key_Home))
        if scrolling_up:
            self.follow_live = False
            self.scroll_timer.stop()
            self.update_follow_button()
        return super().eventFilter(watched, event)

    def resume_live(self):
        self.follow_live = True
        self.update_follow_button()
        self.scroll_timer.start()

    def scroll_to_bottom(self):
        if self.follow_live:
            bar = self.transcript.verticalScrollBar()
            distance = bar.maximum() - bar.value()
            self.updating_scroll = True
            try:
                bar.setValue(bar.value() + max(1, round(distance * .4)) if distance else bar.maximum())
            finally:
                self.updating_scroll = False
            if bar.value() == bar.maximum():
                self.scroll_timer.stop()

    def closeEvent(self, event):
        self.render_timer.stop()
        self.scroll_timer.stop()
        super().closeEvent(event)

    def toggle_minimized(self):
        self.collapsed = not self.collapsed
        self.transcript.setVisible(not self.collapsed)
        self.minimize_button.setText('▢' if self.collapsed else '—')
        self.minimize_button.setToolTip('Expand transcript' if self.collapsed else 'Minimize transcript')
        self.place()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 50:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.user_position = event.globalPosition().toPoint() - self.drag_offset
            self.place()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None
        super().mouseReleaseEvent(event)

    def place(self):
        screens = QApplication.screens()
        screen = screens[min(self.screen_index, len(screens) - 1)]
        rect = screen.availableGeometry()
        width = min(720, int(rect.width() * .46))
        height = 46 if self.collapsed else min(520, int(rect.height() * .55))
        self.setFixedSize(width, height)
        if self.user_position is None:
            self.move(rect.x() + 20, rect.bottom() - self.height() - 38)
        else:
            self.move(max(rect.left(), min(self.user_position.x(), rect.right() - width + 1)),
                      max(rect.top(), min(self.user_position.y(), rect.bottom() - height + 1)))


class Window(QWidget):
    def __init__(self, load_models=True):
        super().__init__()
        self.setWindowTitle('Translate Anything')
        self.resize(620, 720)
        self.events = Events()
        self.overlay = Overlay()
        self.capture = None
        self.active = False
        self.loaded = False
        self.latest = (-1, -1)
        self.latest_translation = (-1, -1)
        self.last_translations = {}
        self.last_original = ''
        self.settings_path = ROOT / 'settings.json'
        try:
            self.settings = json.loads(self.settings_path.read_text('utf-8'))
        except (OSError, ValueError):
            self.settings = {}
        self.setStyleSheet('''
            QWidget { background: #101724; color: #e8edf5; font-family: "Segoe UI"; font-size: 14px; }
            QLabel#title { font-size: 30px; font-weight: 700; }
            QLabel#muted { color: #a3b2c9; }
            QPushButton { background: #263449; border: 0; border-radius: 8px; padding: 11px; }
            QPushButton:hover { background: #354a66; }
            QPushButton#start { background: #57dac0; color: #08271f; font-weight: 700; }
            QPushButton:disabled { background: #25303c; color: #7e8a98; }
            QComboBox, QSpinBox, QListWidget { background: #1a2535; border: 1px solid #35465c; border-radius: 6px; padding: 6px; }
            QListWidget::item { padding: 4px; }
            QProgressBar { border: 0; background: #263449; max-height: 6px; }
            QProgressBar::chunk { background: #57dac0; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        title = QLabel('Translate Anything'); title.setObjectName('title'); layout.addWidget(title)
        subtitle = QLabel('Live captions. Every voice, in your languages.'); subtitle.setObjectName('muted'); layout.addWidget(subtitle)
        layout.addWidget(QLabel('Listen to this audio output'))
        device_row = QHBoxLayout()
        self.device = QComboBox(); device_row.addWidget(self.device, 1)
        refresh = QPushButton('Refresh'); refresh.clicked.connect(self.refresh); device_row.addWidget(refresh)
        self.refresh_button = refresh
        layout.addLayout(device_row)
        self.level = QProgressBar(); self.level.setRange(0, 100); self.level.setTextVisible(False); layout.addWidget(self.level)
        mic_row = QHBoxLayout()
        self.include_mic = QCheckBox('Include my microphone')
        self.include_mic.setChecked(self.settings.get('include_mic', False))
        mic_row.addWidget(self.include_mic)
        self.microphone = QComboBox()
        self.microphone.setEnabled(self.include_mic.isChecked())
        self.include_mic.toggled.connect(self.microphone.setEnabled)
        mic_row.addWidget(self.microphone, 1)
        layout.addLayout(mic_row)
        mic_feedback = QHBoxLayout()
        mic_feedback.addWidget(QLabel('Mic signal'))
        self.mic_meter = QProgressBar()
        self.mic_meter.setRange(0, 100)
        self.mic_meter.setTextVisible(False)
        mic_feedback.addWidget(self.mic_meter, 1)
        mic_feedback.addWidget(QLabel('Mic boost'))
        self.mic_gain = QDoubleSpinBox()
        self.mic_gain.setRange(1, 10)
        self.mic_gain.setSingleStep(.5)
        self.mic_gain.setSuffix('×')
        self.mic_gain.setValue(self.settings.get('microphone_gain', 2))
        mic_feedback.addWidget(self.mic_gain)
        layout.addLayout(mic_feedback)
        layout.addWidget(QLabel('Listening languages • languages people will speak'))
        self.auto_listening = QCheckBox('Detect all languages automatically')
        saved_listening = self.settings.get('listening_languages')
        if 'listening_languages' not in self.settings and self.settings.get('source', 'auto') != 'auto':
            saved_listening = [self.settings['source']]
        self.auto_listening.setChecked(saved_listening is None)
        layout.addWidget(self.auto_listening)
        self.listening = QListWidget()
        self.listening.setSelectionMode(QAbstractItemView.NoSelection)
        self.listening.setFixedHeight(105)
        for code, name in LANGUAGES.items():
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if code in (saved_listening or ['en', 'ar']) else Qt.Unchecked)
            self.listening.addItem(item)
        self.listening.setEnabled(not self.auto_listening.isChecked())
        self.auto_listening.toggled.connect(lambda automatic: self.listening.setEnabled(not automatic))
        layout.addWidget(self.listening)
        layout.addWidget(QLabel('Caption languages • check one or more'))
        self.languages = QListWidget(); self.languages.setSelectionMode(QAbstractItemView.NoSelection)
        selected = self.settings.get('targets', ['en', 'ar'])
        for code, name in LANGUAGES.items():
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if code in selected else Qt.Unchecked)
            self.languages.addItem(item)
        layout.addWidget(self.languages, 1)
        controls = QHBoxLayout()
        controls.addWidget(QLabel('Text size'))
        self.size = QSpinBox(); self.size.setRange(12, 44); self.size.setValue(self.settings.get('size', 18)); controls.addWidget(self.size)
        controls.addWidget(QLabel('Display'))
        self.monitor = QComboBox()
        for i, screen in enumerate(QApplication.screens()): self.monitor.addItem(f'{i + 1}: {screen.name()}', i)
        self.size.valueChanged.connect(self.update_overlay_options)
        self.monitor.currentIndexChanged.connect(self.update_overlay_options)
        controls.addWidget(self.monitor, 1)
        preview = QPushButton('Preview'); preview.clicked.connect(self.preview); controls.addWidget(preview)
        layout.addLayout(controls)
        self.status = QLabel('Preparing local models…'); self.status.setWordWrap(True); self.status.setObjectName('muted'); layout.addWidget(self.status)
        self.start = QPushButton('Loading models…'); self.start.setObjectName('start'); self.start.setEnabled(False); self.start.clicked.connect(self.toggle); layout.addWidget(self.start)
        note = QLabel('Nemotron 3.5 ASR + local translation. No API key.\nTranslations update during speech and settle after each pause.')
        note.setWordWrap(True); note.setObjectName('muted'); layout.addWidget(note)
        if sys.platform == 'darwin':
            help_text = QLabel('Mac system audio: install BlackHole 2ch and select a Multi-Output Device in Sound settings. See START HERE.md. Allow microphone access when asked.')
            help_text.setWordWrap(True)
            layout.addWidget(help_text)
        from .version import VERSION
        self.update_status = QLabel(f'Version {VERSION} • updates checked automatically')
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)
        self.events.update.connect(self.update_status.setText)
        self.events.status.connect(self.report_status)
        self.events.level.connect(self.level.setValue)
        self.events.mic_level.connect(self.mic_meter.setValue)
        self.events.caption.connect(self.on_caption)
        self.events.ready.connect(self.on_ready)
        self.engine = Engine(self.events.status.emit, self.events.caption.emit, self.events.ready.emit)
        self.refresh()
        if load_models:
            self.engine.thread.start()
            from .updater import check
            self.update_thread = threading.Thread(target=check, args=(ROOT, self.events.update.emit), daemon=True)
            self.update_thread.start()

    def refresh(self):
        self.device.clear()
        try:
            for index, name, default in devices():
                self.device.addItem(name, index)
                if default: self.device.setCurrentIndex(self.device.count() - 1)
        except Exception as exc:
            self.status.setText(f'Cannot find a loopback audio device: {exc}')
        self.microphone.clear()
        try:
            for index, name, default in microphones():
                self.microphone.addItem(name, index)
                if default:
                    self.microphone.setCurrentIndex(self.microphone.count() - 1)
            saved_index = self.microphone.findText(self.settings.get('microphone', ''))
            if saved_index >= 0:
                self.microphone.setCurrentIndex(saved_index)
        except Exception as exc:
            self.microphone.setToolTip(f'Microphone unavailable: {exc}')

    def report_status(self, message):
        self.status.setText(message)
        print(f'{time.strftime("%H:%M:%S")} {message}', flush=True)

    def targets(self):
        return [self.languages.item(i).data(Qt.UserRole) for i in range(self.languages.count())
                if self.languages.item(i).checkState() == Qt.Checked]

    def listening_choices(self):
        if self.auto_listening.isChecked():
            return None
        return [self.listening.item(i).data(Qt.UserRole) for i in range(self.listening.count())
                if self.listening.item(i).checkState() == Qt.Checked]

    def on_ready(self):
        self.loaded = True
        self.start.setEnabled(True)
        self.start.setText('Start live captions')
        self.status.setText('Ready • choose languages, then start')

    def preview(self):
        self.overlay.font_size = self.size.value()
        self.overlay.screen_index = self.monitor.currentIndex()
        if not self.overlay.history:
            self.overlay.display('', {'en': 'Hello! How are you today?', 'ar': 'مرحباً! كيف حالك اليوم؟'})
        self.overlay.place()
        self.overlay.show()

    def update_overlay_options(self):
        self.overlay.font_size = self.size.value()
        self.overlay.screen_index = self.monitor.currentIndex()
        if self.overlay.isVisible():
            self.overlay.render()
            self.overlay.place()

    def toggle(self):
        if self.active:
            self.active = False
            self.engine.session += 1
            self.capture.close()
            self.capture = None
            self.mic_meter.setValue(0)
            self.start.setText('Start live captions')
            self.status.setText('Stopped • transcript remains visible')
        else:
            if self.listening_choices() == []:
                QMessageBox.information(self, 'Choose listening languages',
                                        'Check at least one listening language, or enable automatic detection of all languages.')
                return
            if self.device.currentData() == -1 and not self.include_mic.isChecked():
                QMessageBox.information(self, 'Enable the microphone',
                                        'Check Include my microphone, or set up BlackHole to caption system audio. See START HERE.md.')
                return
            if not self.targets() or self.device.currentData() is None:
                QMessageBox.information(self, 'Choose languages and audio', 'Select an output device and at least one caption language.')
                return
            if self.include_mic.isChecked() and self.microphone.currentData() is None:
                QMessageBox.information(self, 'Choose a microphone', 'Select an available microphone or uncheck Include my microphone.')
                return
            self.engine.session += 1
            self.engine.targets = self.targets()
            self.engine.language = 'auto'
            self.engine.listening_languages = self.listening_choices()
            self.overlay.font_size = self.size.value()
            self.overlay.screen_index = self.monitor.currentIndex()
            self.latest = (-1, -1)
            self.latest_translation = (-1, -1)
            self.last_translations = {}
            self.last_original = ''
            self.overlay.history.pop((-1, 1), None)
            self.active = True
            self.capture = Capture(self.device.currentData(), self.engine.submit,
                                   self.events.status.emit, self.events.level.emit,
                                   microphone=self.microphone.currentData() if self.include_mic.isChecked() else None,
                                   mic_level=self.events.mic_level.emit, microphone_gain=self.mic_gain.value())
            self.capture.start()
            self.start.setText('Stop captions')
            self.save()
        for widget in (self.auto_listening, self.device, self.languages, self.refresh_button, self.include_mic, self.mic_gain):
            widget.setEnabled(not self.active)
        self.listening.setEnabled(not self.active and not self.auto_listening.isChecked())
        self.microphone.setEnabled(not self.active and self.include_mic.isChecked())

    def on_caption(self, identity, original, translations, final):
        if not self.active or identity[0] != self.engine.session:
            return
        if translations:
            if identity >= self.latest_translation:
                self.latest_translation = identity
                self.last_translations = translations
        elif identity >= self.latest:
            self.latest = identity
            self.last_original = original
        else:
            return
        self.overlay.update_caption(identity, original, translations, final)

    def save(self):
        data = {'targets': self.targets(), 'listening_languages': self.listening_choices(), 'size': self.size.value(),
                'include_mic': self.include_mic.isChecked(), 'microphone': self.microphone.currentText()}
        data['microphone_gain'] = self.mic_gain.value()
        temp = self.settings_path.with_suffix('.tmp')
        temp.write_text(json.dumps(data), 'utf-8')
        temp.replace(self.settings_path)

    def closeEvent(self, event):
        self.active = False
        if self.capture: self.capture.close()
        self.engine.stop.set()
        if self.engine.thread.is_alive(): self.engine.thread.join(timeout=3)
        if self.engine.translation_thread.is_alive(): self.engine.translation_thread.join(timeout=3)
        self.overlay.close()
        self.save()
        event.accept()


def main():
    app = QApplication([])
    app.setApplicationName('Translate Anything')
    window = Window()
    window.show()
    return app.exec()
