from PyQt5.Qt import Qt, QPushButton, QLabel, QVBoxLayout, QToolButton, QIcon, QFontMetrics

class ToolButton(QToolButton):
    def __init__(self, name, slot=None, tip=None, parent=None):
        QToolButton.__init__(self, parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setIcon(QIcon(name))
        if slot: self.clicked.connect(slot)
        if tip:  self.setToolTip(tip)

class NoFocusButton(QPushButton):
    def __init__(self, text, slot=None, parent=None, enable=True):
        QPushButton.__init__(self, text, parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setEnabled(enable)
        if slot is None: slot = lambda: print(text)
        if slot:         self.clicked.connect(slot) # allow to set no slot by providing False

class ButtonLabel(QLabel):
    def __init__(self, label, parent):
        QLabel.__init__(self, parent)
        self.setText(label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.parent().click()           

class SubtitleButton(NoFocusButton):
    def __init__(self, slot=None, parent=None):
        NoFocusButton.__init__(self, '', self.was_clicked, parent)        
        
        self.main = ButtonLabel('', self)
        self.sub  = ButtonLabel('', self)

        self.main.setAlignment(Qt.AlignBottom)
        self.sub.setAlignment(Qt.AlignTop)        
        
        v = QVBoxLayout(self)
        v.setSpacing(0)
        v.addWidget(self.main)
        v.addWidget(self.sub )
        self.setLayout(v)

    def scale_fonts(self, new):
        for w,fac in zip((self.main, self.sub),(1.125, 0.8)):
            f = w.font()
            f.setPointSize(round(new*fac))
            w.setFont(f)

        # measure actual rendered text height instead of guessing per-OS pixel offsets,
        # so labels never get clipped when the system's default font/DPI differs
        padding = 10
        height  = QFontMetrics(self.main.font()).height() + QFontMetrics(self.sub.font()).height() + padding
        self.setMinimumHeight(height)

    def setText(self, text, sub=None):
        self.main.setText(text)
        if sub is not None: self.sub.setText(sub)
