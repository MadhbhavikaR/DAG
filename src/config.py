from typing import Dict

from calibre_plugins.store_annas_archive.constants import (DEFAULT_MIRRORS, SearchConfiguration, Order, Content, Access,
                                                           FileType, Source, Language)

try:
    from qt.core import (Qt, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox, QScrollArea,
                         QAbstractScrollArea, QComboBox, QCheckBox, QSizePolicy, QListWidget, QListWidgetItem, QPushButton,
                         QAbstractItemView, QShortcut, QKeySequence)
except (ImportError, ModuleNotFoundError):
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox, QScrollArea,
                                 QAbstractScrollArea, QComboBox, QCheckBox, QSizePolicy, QListWidget, QListWidgetItem, QPushButton,
                                 QAbstractItemView, QShortcut)
    from PyQt5.QtGui import QKeySequence

load_translations()


class MirrorsList(QListWidget):
    """Editable list of mirrors managed with explicit add, edit, and delete actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def load_mirrors(self, mirrors):
        self.clear()
        for mirror in mirrors:
            self._append_item(str(mirror))

    def _append_item(self, value=''):
        item = QListWidgetItem(value, self)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsDragEnabled)
        return item

    def add_mirror(self):
        item = self._append_item()
        self.setCurrentItem(item)
        self.editItem(item)

    def edit_mirror(self):
        item = self.currentItem()
        if item is not None:
            self.editItem(item)

    def delete_mirror(self):
        row = self.currentRow()
        if row >= 0:
            self.takeItem(row)

    def get_mirrors(self) -> list:
        mirrors = []
        for i in range(self.count()):
            mirror = str(self.item(i).text()).strip().rstrip('/')
            if mirror and mirror not in mirrors:
                mirrors.append(mirror)
        return mirrors


class ConfigWidget(QWidget):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.resize(635, 780)

        main_layout = QVBoxLayout(self)

        search_options = QGroupBox(_('Search options'), self)
        search_options.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        search_grid = QGridLayout(search_options)
        search_grid.setContentsMargins(3, 3, 3, 3)

        ordering_label = QLabel(_('Ordering:'), search_options)
        ordering_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        search_grid.addWidget(ordering_label, 0, 0)
        order = QComboBox(search_options)
        for txt, value in Order.options:
            order.addItem(txt, value)
        order.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        search_grid.addWidget(order, 0, 1)
        self.order = Order(order)

        self.search_options: Dict[str, SearchConfiguration] = {self.order.config_option: self.order}

        # TODO: lay the options out better
        search_grid.addWidget(self._make_cbx_group(search_options, Content()), 1, 0)
        search_grid.addWidget(self._make_cbx_group(search_options, FileType()), 2, 0)
        search_grid.addWidget(self._make_cbx_group(search_options, Access()), 1, 1)
        search_grid.addWidget(self._make_cbx_group(search_options, Source()), 2, 1)
        search_grid.addWidget(self._make_cbx_group(search_options, Language(), scrollbar=True), 1, 2, 2, 1)

        main_layout.addWidget(search_options)

        horizontal_layout = QHBoxLayout()

        link_options = QGroupBox(_('Download link options'), self)
        link_options.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        link_layout = QVBoxLayout(link_options)
        link_layout.setContentsMargins(6, 6, 6, 6)
        self.url_extension = QCheckBox(_('Verify url extension'), link_options)
        self.url_extension.setToolTip(_('Verify that the each download url ends with correct extension for the format'))
        link_layout.addWidget(self.url_extension)
        self.content_type = QCheckBox(_('Verify Content-Type'), link_options)
        self.content_type.setToolTip(_(
            'Get the header of each site and verify that it has an \'application\' content type'))
        link_layout.addWidget(self.content_type)
        horizontal_layout.addWidget(link_options)

        mirrors = QGroupBox(_('Mirrors'), self)
        layout = QVBoxLayout(mirrors)
        layout.setContentsMargins(1, 1, 1, 1)
        self.mirrors = MirrorsList(mirrors)
        layout.addWidget(self.mirrors)
        mirror_buttons = QHBoxLayout()
        add_mirror = QPushButton(_('Add'), mirrors)
        add_mirror.clicked.connect(self.mirrors.add_mirror)
        edit_mirror = QPushButton(_('Edit'), mirrors)
        edit_mirror.clicked.connect(self.mirrors.edit_mirror)
        delete_mirror = QPushButton(_('Delete'), mirrors)
        delete_mirror.clicked.connect(self.mirrors.delete_mirror)
        mirror_buttons.addWidget(add_mirror)
        mirror_buttons.addWidget(edit_mirror)
        mirror_buttons.addWidget(delete_mirror)
        layout.addLayout(mirror_buttons)
        horizontal_layout.addWidget(mirrors)

        main_layout.addLayout(horizontal_layout)

        self.open_external = QCheckBox(_('Open store in external web browser'), self)
        main_layout.addWidget(self.open_external)

        self.load_settings()

    def _make_cbx_group(self, parent, option: SearchConfiguration, scrollbar: bool = False):
        box = QGroupBox(_(option.name), parent)
        vertical_layout = QVBoxLayout(box)
        if scrollbar:
            vertical_layout.setSpacing(0)
            vertical_layout.setContentsMargins(0, 0, 0, 0)

            scroll_area = QScrollArea(box)
            scroll_area.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
            scroll_area.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)

            cbx_parent = QWidget()
            cbx_parent.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            top_vertical = vertical_layout
            vertical_layout = QVBoxLayout(cbx_parent)
        else:
            cbx_parent = box

        vertical_layout.setSpacing(3)
        vertical_layout.setContentsMargins(3, 3, 3, 3)

        for name, type_ in option.options:
            check_box = QCheckBox(cbx_parent)
            check_box.setText(name)
            vertical_layout.addWidget(check_box)
            option.checkboxes[type_] = check_box
        self.search_options[option.config_option] = option
        if scrollbar:
            scroll_area.setWidget(cbx_parent)
            top_vertical.addWidget(scroll_area)
        return box

    def load_settings(self):
        config = self.store.config

        self.open_external.setChecked(config.get('open_external', False))
        configured_mirrors = config.get('mirrors')
        # Migrate the previous built-in mirror set, preserving custom user lists.
        old_defaults = ['https://annas-archive.org', 'https://annas-archive.li', 'https://annas-archive.se']
        if configured_mirrors is None or configured_mirrors == old_defaults:
            configured_mirrors = DEFAULT_MIRRORS
        self.mirrors.load_mirrors(configured_mirrors)

        search_opts = config.get('search', {})
        for configuration in self.search_options.values():
            configuration.load(search_opts.get(configuration.config_option, configuration.default))

        link_opts = config.get('link', {})
        self.url_extension.setChecked(link_opts.get('url_extension', True))
        self.content_type.setChecked(link_opts.get('content_type', False))

    def save_settings(self):
        self.store.config['open_external'] = self.open_external.isChecked()
        self.store.config['mirrors'] = self.mirrors.get_mirrors()

        self.store.config['search'] = {
            configuration.config_option: configuration.to_save()
            for configuration in self.search_options.values()
        }
        self.store.config['link'] = {
            'url_extension': self.url_extension.isChecked(),
            'content_type': self.content_type.isChecked()
        }
