import tempfile
from pathlib import Path

from PyQt5.Qt import Qt, QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLineEdit, \
    QLabel, QFileDialog, QPixmap, QImage, QIcon

from webola.buttons import NoFocusButton
from webola.pdf_urkunde import UrkundeImages, generate_preview_pdf

IMAGE_FILTER = 'Bilder (*.png *.jpg *.jpeg)'


class ImageRow(QHBoxLayout):
    def __init__(self, label, initial, parent):
        QHBoxLayout.__init__(self)
        self.edit = QLineEdit(initial)
        self.edit.setReadOnly(True)
        browse = NoFocusButton('...', lambda: self.browse(label, parent))

        self.addWidget(QLabel(label))
        self.addWidget(self.edit, 1)
        self.addWidget(browse)

    def browse(self, label, parent):
        name, _ = QFileDialog.getOpenFileName(parent, f'{label} wählen ...', self.edit.text(), IMAGE_FILTER)
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
