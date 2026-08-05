import tempfile
from pathlib import Path

from PyQt5.Qt import Qt, QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLineEdit, \
    QLabel, QFileDialog, QPixmap, QImage, QIcon

from webola.buttons import NoFocusButton
from webola.pdf_urkunde import UrkundeImages, generate_preview_pdf, render_text_on_template_preview

IMAGE_FILTER    = 'Bilder (*.png *.jpg *.jpeg)'
TEMPLATE_FILTER = 'PDF Dateien (*.pdf)'


class ImageRow(QHBoxLayout):
    def __init__(self, label, initial, parent, file_filter=IMAGE_FILTER):
        QHBoxLayout.__init__(self)
        self.edit = QLineEdit(initial)
        self.edit.setReadOnly(True)
        self.label  = label
        self.parent = parent
        self.filter = file_filter
        browse = NoFocusButton('...', self.browse)

        self.addWidget(QLabel(label))
        self.addWidget(self.edit, 1)
        self.addWidget(browse)

    def browse(self):
        name, _ = QFileDialog.getOpenFileName(self.parent, f'{self.label} wählen ...', self.edit.text(), self.filter)
        if name:
            self.edit.setText(name)

    def path(self):
        return self.edit.text()


class UrkundenImagesDialog(QDialog):
    def __init__(self, images):
        QDialog.__init__(self)
        self.setWindowIcon(QIcon(":/webola.png"))
        self.setWindowTitle('Urkunden-Layout: Bilder wählen')

        self.head  = ImageRow('Kopfbild (oben)'        , images.head , self)
        self.left  = ImageRow('Bild unten links'        , images.left , self)
        self.right = ImageRow('Bild unten rechts'       , images.right, self)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.try_accept)
        button_box.rejected.connect(self.reject)
        for b in button_box.buttons():
            b.setFocusPolicy(Qt.NoFocus)

        info = QLabel('Für die Urkunden-PDF-Erzeugung werden drei Bilder benötigt: '
                       'ein Kopfbild (mittig oben) und je ein Bild unten links/rechts.')
        info.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(info)
        layout.addLayout(self.head)
        layout.addLayout(self.left)
        layout.addLayout(self.right)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def try_accept(self):
        if not self.images().valid():
            return  # simply ignore -- user still has to pick all three
        self.accept()

    def images(self):
        return UrkundeImages(head=self.head.path(), left=self.left.path(), right=self.right.path())


class UrkundenPreviewDialog(QDialog):
    def __init__(self, images):
        QDialog.__init__(self)
        self.setWindowIcon(QIcon(":/webola.png"))
        self.setWindowTitle('Urkunden-Vorschau')

        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        pixmap = self._render_preview(images)
        if pixmap:
            preview.setPixmap(pixmap)
        else:
            preview.setText('Vorschau konnte nicht erzeugt werden.')

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Ok).setText('Urkunden erstellen')
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        for b in button_box.buttons():
            b.setFocusPolicy(Qt.NoFocus)

        layout = QVBoxLayout()
        layout.addWidget(preview)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def _render_preview(self, images):
        import fitz  # PyMuPDF -- pure-Python, no external binary, used only for this preview render

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / 'preview.pdf'
            generate_preview_pdf(pdf_path, images)

            doc  = fitz.open(str(pdf_path))
            page = doc[0]
            pix  = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            fmt  = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            pixmap = QPixmap.fromImage(qimg.copy())
            doc.close()

            screen_height = 800
            if pixmap.height() > screen_height:
                pixmap = pixmap.scaledToHeight(screen_height, Qt.SmoothTransformation)
            return pixmap


class UrkundenTemplateDialog(QDialog):
    """Picks the pre-printed template PDF -- used ONLY locally to render a
    WYSIWYG preview of where the text will land. Never read again at
    generation time and never embedded in the generated output."""

    def __init__(self, initial):
        QDialog.__init__(self)
        self.setWindowIcon(QIcon(":/webola.png"))
        self.setWindowTitle('Urkunden-Vordruck: PDF wählen')

        self.template = ImageRow('Vordruck (PDF)', initial, self, file_filter=TEMPLATE_FILTER)

        info = QLabel('Für die Vorschau wird die Vordruck-PDF-Datei benötigt (bereits bedrucktes Papier: '
                       'Kopfbild, "URKUNDE"-Schriftzug, Unterschriften). Beim eigentlichen Erstellen der '
                       'Urkunden wird nur der Text erzeugt -- die Vordruck-PDF wird dafür nicht benötigt.')
        info.setWordWrap(True)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.try_accept)
        button_box.rejected.connect(self.reject)
        for b in button_box.buttons():
            b.setFocusPolicy(Qt.NoFocus)

        layout = QVBoxLayout()
        layout.addWidget(info)
        layout.addLayout(self.template)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def try_accept(self):
        if not self.path():
            return
        self.accept()

    def path(self):
        return self.template.path()


class UrkundenTextPreviewDialog(QDialog):
    def __init__(self, template_path):
        QDialog.__init__(self)
        self.setWindowIcon(QIcon(":/webola.png"))
        self.setWindowTitle('Urkunden-Vorschau (Text auf Vordruck)')

        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        pixmap = self._render_preview(template_path)
        if pixmap:
            preview.setPixmap(pixmap)
        else:
            preview.setText('Vorschau konnte nicht erzeugt werden.')

        note = QLabel('Nur eine Vorschau -- beim Erstellen wird ausschließlich der Text erzeugt, '
                       'nicht der Vordruck selbst.')
        note.setWordWrap(True)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Ok).setText('Urkunden erstellen')
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        for b in button_box.buttons():
            b.setFocusPolicy(Qt.NoFocus)

        layout = QVBoxLayout()
        layout.addWidget(preview)
        layout.addWidget(note)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def _render_preview(self, template_path):
        try:
            img = render_text_on_template_preview(template_path)
        except Exception:
            return None

        qimg = QImage(img.tobytes(), img.width, img.height, img.width * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg.copy())

        screen_height = 800
        if pixmap.height() > screen_height:
            pixmap = pixmap.scaledToHeight(screen_height, Qt.SmoothTransformation)
        return pixmap
