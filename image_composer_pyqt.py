import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
                             QGraphicsPixmapItem, QFileDialog, QMessageBox, QToolBar,
                             QAction, QStatusBar, QGraphicsItem, QSizePolicy, QPushButton,
                             QWidget, QHBoxLayout, QSystemTrayIcon, QMenu, QDialog,
                             QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QStyle,
                             QGraphicsLineItem, QGraphicsPolygonItem, QGraphicsItemGroup,
                             QGraphicsRectItem, QListWidget, QListWidgetItem, QAbstractItemView,
                             QCheckBox, QGraphicsTextItem, QInputDialog, QTextEdit)
from PyQt5.QtCore import Qt, QPointF, QRectF, QSize, QPropertyAnimation, pyqtProperty, QSettings, pyqtSignal, QObject, QLineF, QTimer, QUrl
from PyQt5.QtGui import QPixmap, QImage, QPainter, QKeySequence, QIcon, QPen, QColor, QPolygonF, QBrush, QFont
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PIL import Image
import os
from datetime import datetime
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 从环境变量获取输入目录，默认为 OneDrive\图片\Screenshots
INPUT_DIR = os.getenv('INPUT_DIR', os.path.join(os.path.expanduser("~"), "OneDrive", "图片", "Screenshots"))
# 从环境变量获取桌面目录，默认为 OneDrive\Desktop
DESKTOP_DIR = os.getenv('desktop_dir', os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"))
import ctypes

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False


# ===== 快照管理系统 =====

class SnapshotManager:
    """快照管理器 - 保存和恢复画布状态"""
    def __init__(self):
        self.snapshots = []  # 快照列表
        self.max_snapshots = 50  # 最大快照数量

    def save_snapshot(self, scene, image_items_data):
        """
        保存当前画布状态为快照
        scene: QGraphicsScene
        image_items_data: 图片项的原始数据列表
        """
        snapshot = {
            'images': [],
            'arrows': [],
            'lines': [],
            'rects': [],
            'texts': []
        }

        for item in scene.items():
            if isinstance(item, DraggablePixmapItem):
                snapshot['images'].append({
                    'pixmap': item.pixmap().copy(),
                    'original_image': item.original_image.copy() if item.original_image else None,
                    'pos': QPointF(item.pos()),
                    'z_value': item.zValue(),
                    'user_scale': item.user_scale,
                    'file_path': item.file_path
                })
            elif isinstance(item, ArrowItem):
                snapshot['arrows'].append({
                    'start': QPointF(item.start_point),
                    'end': QPointF(item.end_point),
                    'pos': QPointF(item.pos()),
                    'z_value': item.zValue()
                })
            elif isinstance(item, LineItem):
                snapshot['lines'].append({
                    'start': QPointF(item.start_point),
                    'end': QPointF(item.end_point),
                    'pos': QPointF(item.pos()),
                    'z_value': item.zValue()
                })
            elif isinstance(item, RectItem):
                snapshot['rects'].append({
                    'start': QPointF(item.start_point),
                    'end': QPointF(item.end_point),
                    'pos': QPointF(item.pos()),
                    'z_value': item.zValue()
                })
            elif isinstance(item, TextItem):
                snapshot['texts'].append({
                    'text': item.toPlainText(),
                    'pos': QPointF(item.pos()),
                    'z_value': item.zValue(),
                    'font_size': item.font_size
                })

        self.snapshots.append(snapshot)

        # 限制快照数量
        if len(self.snapshots) > self.max_snapshots:
            self.snapshots.pop(0)

        return len(self.snapshots)

    def restore_snapshot(self, scene):
        """恢复到上一个快照状态"""
        if len(self.snapshots) < 2:
            return False, 0

        # 移除当前状态（最后一个快照）
        self.snapshots.pop()

        # 获取要恢复的快照
        snapshot = self.snapshots[-1]

        # 清空当前场景
        scene.clear()

        # 恢复图片
        for img_data in snapshot['images']:
            item = DraggablePixmapItem(
                img_data['pixmap'],
                img_data['original_image'],
                file_path=img_data['file_path']
            )
            item.user_scale = img_data['user_scale']
            item.setScale(img_data['user_scale'])
            item.setPos(img_data['pos'])
            item.setZValue(img_data['z_value'])
            scene.addItem(item)

        # 恢复箭头
        for arrow_data in snapshot['arrows']:
            arrow = ArrowItem(arrow_data['start'], arrow_data['end'])
            arrow.setPos(arrow_data['pos'])
            arrow.setZValue(arrow_data['z_value'])
            scene.addItem(arrow)

        # 恢复线条
        for line_data in snapshot['lines']:
            line = LineItem(line_data['start'], line_data['end'])
            line.setPos(line_data['pos'])
            line.setZValue(line_data['z_value'])
            scene.addItem(line)

        # 恢复矩形
        for rect_data in snapshot['rects']:
            rect = RectItem(rect_data['start'], rect_data['end'])
            rect.setPos(rect_data['pos'])
            rect.setZValue(rect_data['z_value'])
            scene.addItem(rect)

        # 恢复文字
        for text_data in snapshot['texts']:
            text = TextItem(text_data['text'], text_data['pos'], text_data['font_size'])
            text.setZValue(text_data['z_value'])
            scene.addItem(text)

        return True, len(self.snapshots)

    def get_snapshot_count(self):
        """获取当前快照数量"""
        return len(self.snapshots)

    def clear(self):
        """清空所有快照"""
        self.snapshots.clear()

    def has_snapshots(self):
        """是否有快照可以撤销"""
        return len(self.snapshots) > 1


# 保留旧的类名以兼容
class DrawingUndoStack:
    """绘图操作撤销栈 - 支持箭头、线条、矩形、文字的撤销"""
    def __init__(self):
        self.undo_stack = []  # 存储操作记录: {'type': 'add'/'delete', 'scene': scene, 'items': [items]}

    def push_add_item(self, scene, item):
        """记录添加绘图元素的操作"""
        self.undo_stack.append({
            'type': 'add',
            'scene': scene,
            'items': [item]
        })

    def push_delete_items(self, scene, items):
        """记录删除绘图元素的操作"""
        if items:
            self.undo_stack.append({
                'type': 'delete',
                'scene': scene,
                'items': list(items)
            })

    def undo(self):
        """撤销最近一次绘图操作"""
        if not self.undo_stack:
            return False

        action = self.undo_stack.pop()
        scene = action['scene']
        items = action['items']

        if action['type'] == 'add':
            # 撤销添加操作 = 删除元素
            for item in items:
                if item.scene() == scene:
                    scene.removeItem(item)
        elif action['type'] == 'delete':
            # 撤销删除操作 = 恢复元素
            for item in items:
                scene.addItem(item)

        return True

    def redo(self):
        return False

    def can_undo(self):
        """是否有操作可以撤销"""
        return len(self.undo_stack) > 0

    def can_redo(self):
        return False

    def clear(self):
        """清空撤销栈"""
        self.undo_stack.clear()


class HotkeySignalEmitter(QObject):
    """用于从keyboard库线程发送信号到Qt主线程的信号发射器"""
    show_signal = pyqtSignal()


class CustomImagePicker(QDialog):
    """自定义图片选择器，按创建时间排序，只显示最新5张"""
    def __init__(self, default_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择图片文件 (最新5张)")
        self.setModal(True)
        self.resize(900, 700)

        self.selected_files = []
        self.default_path = default_path

        self.init_ui()
        self.load_images()

    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()

        # 路径显示标签
        self.path_label = QLabel(f"目录: {self.default_path}")
        self.path_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.path_label)

        # 提示信息
        info_label = QLabel("显示最新的5张图片，按创建时间从新到旧排序。双击或勾选文件进行选择。")
        info_label.setStyleSheet("color: gray; font-size: 11px; padding: 5px;")
        layout.addWidget(info_label)

        # 文件列表
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setIconSize(QSize(200, 200))  # 设置大尺寸高清缩略图
        self.file_list.setSpacing(10)  # 增加项目间距
        self.file_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.file_list)

        # 底部按钮栏
        button_layout = QHBoxLayout()

        # 全选/取消全选
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(self.deselect_all_btn)

        button_layout.addStretch()

        # 确认/取消按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept_selection)
        buttons.rejected.connect(self.reject)
        button_layout.addWidget(buttons)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def load_images(self):
        """加载图片文件并按创建时间排序"""
        if not os.path.exists(self.default_path):
            self.path_label.setText(f"目录不存在: {self.default_path}")
            return

        # 支持的图片格式
        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')

        # 获取所有图片文件及其创建时间
        files_with_time = []
        for filename in os.listdir(self.default_path):
            if filename.lower().endswith(image_extensions):
                file_path = os.path.join(self.default_path, filename)
                try:
                    # 获取文件创建时间
                    create_time = os.path.getctime(file_path)
                    files_with_time.append((file_path, filename, create_time))
                except Exception:
                    continue

        # 按创建时间从新到旧排序（时间大的在前）
        files_with_time.sort(key=lambda x: x[2], reverse=True)

        # 只取前5张图片
        files_with_time = files_with_time[:5]

        # 加载前5张图片（带高清缩略图）
        for file_path, filename, create_time in files_with_time:
            # 格式化时间
            time_str = datetime.fromtimestamp(create_time).strftime("%Y-%m-%d %H:%M:%S")

            # 创建高清缩略图
            try:
                pixmap = QPixmap(file_path)
                if not pixmap.isNull():
                    # 使用高质量缩放，保持宽高比
                    thumbnail = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    icon = QIcon(thumbnail)
                else:
                    icon = QIcon()
            except Exception:
                icon = QIcon()

            # 创建列表项
            item = QListWidgetItem(icon, f"{filename}\n{time_str}")
            item.setData(Qt.UserRole, file_path)  # 存储完整路径
            self.file_list.addItem(item)

        # 更新计数
        total_count = len([f for f in os.listdir(self.default_path)
                          if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))])
        self.path_label.setText(f"目录: {self.default_path}  (显示最新 {len(files_with_time)}/{total_count} 张)")

    def select_all(self):
        """全选"""
        for i in range(self.file_list.count()):
            self.file_list.item(i).setSelected(True)

    def deselect_all(self):
        """取消全选"""
        self.file_list.clearSelection()

    def on_item_double_clicked(self, item):
        """双击文件项，直接选中该文件并关闭对话框"""
        file_path = item.data(Qt.UserRole)
        self.selected_files = [file_path]
        self.accept()

    def accept_selection(self):
        """确认选择"""
        selected_items = self.file_list.selectedItems()
        self.selected_files = [item.data(Qt.UserRole) for item in selected_items]
        self.accept()

    def get_selected_files(self):
        """获取选中的文件列表"""
        return self.selected_files


class MultiLineTextDialog(QDialog):
    """支持Ctrl+Enter确认的多行文本输入对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("输入文本")
        self.setModal(True)
        self.resize(400, 200)

        layout = QVBoxLayout()

        # 提示标签
        label = QLabel("请输入要添加的文字（Ctrl+Enter 确认 | Ctrl+Shift+V 格式化粘贴）：")
        layout.addWidget(label)

        # 多行文本输入框
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("在此输入文字...")
        self.text_edit.installEventFilter(self)
        layout.addWidget(self.text_edit)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def eventFilter(self, obj, event):
        """事件过滤器，处理Ctrl+Enter快捷键 和 Ctrl+Shift+V 格式化粘贴"""
        if obj == self.text_edit and event.type() == event.KeyPress:
            if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
                self.accept()
                return True
            if (event.key() == Qt.Key_V and
                    event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier)):
                clipboard = QApplication.clipboard()
                plain_text = clipboard.text()
                if plain_text:
                    self.text_edit.insertPlainText(plain_text)
                return True
        return super().eventFilter(obj, event)

    def get_text(self):
        """获取输入的文本"""
        return self.text_edit.toPlainText()


class HotkeySettingsDialog(QDialog):
    """快捷键设置对话框"""
    def __init__(self, current_hotkey, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.setModal(True)

        layout = QVBoxLayout()

        # 说明文字
        info_label = QLabel("设置全局快捷键来显示/隐藏窗口")
        layout.addWidget(info_label)

        # 快捷键输入框
        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setText(current_hotkey)
        self.hotkey_edit.setPlaceholderText("例如: ctrl+win+z")
        layout.addWidget(QLabel("快捷键 (使用+连接，如ctrl+shift+a):"))
        layout.addWidget(self.hotkey_edit)

        # 提示
        tip_label = QLabel("支持的修饰键: ctrl, shift, alt, win\n支持的按键: a-z, 0-9, f1-f12等")
        tip_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(tip_label)

        if not KEYBOARD_AVAILABLE:
            warning_label = QLabel("⚠️ 需要安装keyboard库才能使用全局快捷键\n运行: pip install keyboard")
            warning_label.setStyleSheet("color: red;")
            layout.addWidget(warning_label)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_hotkey(self):
        return self.hotkey_edit.text().strip()


class LineItem(QGraphicsItemGroup):
    """可拖拽的细线"""
    def __init__(self, start_point, end_point):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        self.start_point = start_point
        self.end_point = end_point

        # 细线样式 - 使用较细的红色线
        self.pen = QPen(QColor(255, 0, 0), 2, Qt.SolidLine)

        # 创建线条
        self.line = QGraphicsLineItem()

        self.addToGroup(self.line)

        self.update_line()

        self.setCursor(Qt.OpenHandCursor)

    def update_line(self):
        """更新线条的位置"""
        # 设置线条
        line = QLineF(self.start_point, self.end_point)
        self.line.setLine(line)
        self.line.setPen(self.pen)

    def mousePressEvent(self, event):
        self.setCursor(Qt.ClosedHandCursor)
        # 选中时自动置顶
        if self.scene():
            max_z = 0
            for item in self.scene().items():
                if isinstance(item, (DraggablePixmapItem, ArrowItem, LineItem, RectItem)):
                    max_z = max(max_z, item.zValue())
            self.setZValue(max_z + 1)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


class RectItem(QGraphicsItemGroup):
    """可拖拽的矩形框"""
    def __init__(self, start_point, end_point):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        self.start_point = start_point
        self.end_point = end_point

        # 矩形框样式 - 红色边框，无填充
        self.pen = QPen(QColor(255, 0, 0), 3, Qt.SolidLine)

        # 创建矩形
        self.rect = QGraphicsRectItem()

        self.addToGroup(self.rect)

        self.update_rect()

        self.setCursor(Qt.OpenHandCursor)

    def update_rect(self):
        """更新矩形的位置和大小"""
        # 计算矩形区域（处理任意方向的拖拽）
        x = min(self.start_point.x(), self.end_point.x())
        y = min(self.start_point.y(), self.end_point.y())
        width = abs(self.end_point.x() - self.start_point.x())
        height = abs(self.end_point.y() - self.start_point.y())

        self.rect.setRect(x, y, width, height)
        self.rect.setPen(self.pen)
        self.rect.setBrush(QBrush(Qt.transparent))  # 透明填充

    def mousePressEvent(self, event):
        self.setCursor(Qt.ClosedHandCursor)
        # 选中时自动置顶
        if self.scene():
            max_z = 0
            for item in self.scene().items():
                if isinstance(item, (DraggablePixmapItem, ArrowItem, LineItem, RectItem)):
                    max_z = max(max_z, item.zValue())
            self.setZValue(max_z + 1)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


class TextItem(QGraphicsTextItem):
    """可拖拽的红色文本"""
    def __init__(self, text, position, font_size=24):
        super().__init__(text)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        # 设置红色字体
        self.font_size = font_size
        font = QFont("Microsoft YaHei", font_size)
        font.setBold(True)
        self.setFont(font)
        self.setDefaultTextColor(QColor(255, 0, 0))

        # 设置位置
        self.setPos(position)

        self.setCursor(Qt.OpenHandCursor)

    def increase_font_size(self, delta=2):
        """增大字体"""
        self.font_size = min(200, self.font_size + delta)
        font = self.font()
        font.setPointSize(self.font_size)
        self.setFont(font)

    def decrease_font_size(self, delta=2):
        """减小字体"""
        self.font_size = max(8, self.font_size - delta)
        font = self.font()
        font.setPointSize(self.font_size)
        self.setFont(font)

    def mousePressEvent(self, event):
        self.setCursor(Qt.ClosedHandCursor)
        # 选中时自动置顶
        if self.scene():
            max_z = 0
            for item in self.scene().items():
                if isinstance(item, (DraggablePixmapItem, ArrowItem, LineItem, RectItem, TextItem)):
                    max_z = max(max_z, item.zValue())
            self.setZValue(max_z + 1)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


class ArrowItem(QGraphicsItemGroup):
    """可拖拽的箭头"""
    def __init__(self, start_point, end_point):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        

        self.start_point = start_point
        self.end_point = end_point

        # 箭头样式
        self.pen = QPen(QColor(255, 0, 0), 3, Qt.SolidLine)
        self.arrow_size = 15

        # 创建箭头的线条和箭头头部
        self.line = QGraphicsLineItem()
        self.arrow_head = QGraphicsPolygonItem()

        self.addToGroup(self.line)
        self.addToGroup(self.arrow_head)

        self.update_arrow()

        self.setCursor(Qt.OpenHandCursor)

    def update_arrow(self):
        """更新箭头的位置和形状"""
        # 设置线条
        line = QLineF(self.start_point, self.end_point)
        self.line.setLine(line)
        self.line.setPen(self.pen)

        # 计算箭头头部
        arrow_p1 = self.end_point - QPointF(
            self.arrow_size * (line.dx() / line.length() + 0.5 * line.dy() / line.length()),
            self.arrow_size * (line.dy() / line.length() - 0.5 * line.dx() / line.length())
        )
        arrow_p2 = self.end_point - QPointF(
            self.arrow_size * (line.dx() / line.length() - 0.5 * line.dy() / line.length()),
            self.arrow_size * (line.dy() / line.length() + 0.5 * line.dx() / line.length())
        )

        arrow_head_polygon = QPolygonF([self.end_point, arrow_p1, arrow_p2])
        self.arrow_head.setPolygon(arrow_head_polygon)
        self.arrow_head.setPen(self.pen)
        self.arrow_head.setBrush(QBrush(self.pen.color()))

    def mousePressEvent(self, event):
        self.setCursor(Qt.ClosedHandCursor)
        # 选中时自动置顶
        if self.scene():
            max_z = 0
            for item in self.scene().items():
                if isinstance(item, (DraggablePixmapItem, ArrowItem, LineItem, RectItem)):
                    max_z = max(max_z, item.zValue())
            self.setZValue(max_z + 1)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


class DraggablePixmapItem(QGraphicsPixmapItem):
    """可拖拽的图片项"""
    def __init__(self, pixmap, original_image, display_scale=1.0, file_path=None):
        super().__init__(pixmap)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setTransformationMode(Qt.SmoothTransformation)

        # 保存原始图片和显示缩放比例
        self.original_image = original_image
        self.display_scale = display_scale  # 原始图片到显示图片的缩放比例
        self.user_scale = 1.0  # 用户编辑时的缩放比例
        self.file_path = file_path  # 保存原始文件路径

        # 设置变换原点为中心
        self.setTransformOriginPoint(self.boundingRect().center())

        # 设置光标
        self.setCursor(Qt.OpenHandCursor)

    def scale_by(self, factor):
        """按比例缩放图片"""
        self.user_scale *= factor
        self.setScale(self.user_scale)

    def mousePressEvent(self, event):
        self.setCursor(Qt.ClosedHandCursor)
        # 选中时自动置顶：找到场景中所有图片的最大Z值，然后设置为比它更大
        if self.scene():
            max_z = 0
            for item in self.scene().items():
                if isinstance(item, DraggablePixmapItem):
                    max_z = max(max_z, item.zValue())
            self.setZValue(max_z + 1)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


class CustomGraphicsView(QGraphicsView):
    """自定义图形视图，支持箭头绘制"""
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.main_window = None

    def mousePressEvent(self, event):
        if self.main_window and self.main_window.arrow_mode and event.button() == Qt.LeftButton:
            # 箭头绘制模式
            scene_pos = self.mapToScene(event.pos())
            self.main_window.arrow_start_point = scene_pos

            # 创建临时线条用于预览
            pen = QPen(QColor(255, 0, 0, 150), 3, Qt.DashLine)
            self.main_window.temp_arrow_line = self.scene().addLine(
                scene_pos.x(), scene_pos.y(), scene_pos.x(), scene_pos.y(), pen
            )
            # 重置定时器（用户有操作）
            self.main_window.arrow_mode_timer.start(60000)
            event.accept()  # 标记事件已处理
        elif self.main_window and self.main_window.line_mode and event.button() == Qt.LeftButton:
            # 画线绘制模式
            scene_pos = self.mapToScene(event.pos())
            self.main_window.line_start_point = scene_pos

            # 创建临时线条用于预览
            pen = QPen(QColor(255, 0, 0, 150), 2, Qt.DashLine)
            self.main_window.temp_line = self.scene().addLine(
                scene_pos.x(), scene_pos.y(), scene_pos.x(), scene_pos.y(), pen
            )
            # 重置定时器（用户有操作）
            self.main_window.line_mode_timer.start(60000)
            event.accept()  # 标记事件已处理
        elif self.main_window and self.main_window.rect_mode and event.button() == Qt.LeftButton:
            # 矩形绘制模式
            scene_pos = self.mapToScene(event.pos())
            self.main_window.rect_start_point = scene_pos

            # 创建临时矩形用于预览
            pen = QPen(QColor(255, 0, 0, 150), 3, Qt.DashLine)
            self.main_window.temp_rect = self.scene().addRect(
                scene_pos.x(), scene_pos.y(), 0, 0, pen
            )
            # 重置定时器（用户有操作）
            self.main_window.rect_mode_timer.start(60000)
            event.accept()  # 标记事件已处理
        elif self.main_window and self.main_window.text_mode and event.button() == Qt.LeftButton:
            # 文本输入模式
            scene_pos = self.mapToScene(event.pos())

            # 检查点击位置是否有现有的 TextItem（需要临时启用项目来检测）
            existing_text_item = None
            for item in self.scene().items(scene_pos):
                if isinstance(item, TextItem):
                    existing_text_item = item
                    break

            # 弹出多行文本输入对话框（支持Ctrl+Enter确认）
            dialog = MultiLineTextDialog(self.main_window)
            if existing_text_item:
                # 编辑现有文本
                dialog.setWindowTitle("编辑文本")
                dialog.text_edit.setPlainText(existing_text_item.toPlainText())

            if dialog.exec_() == QDialog.Accepted:
                text = dialog.get_text()
                if existing_text_item:
                    # 更新现有文本
                    if text.strip():
                        existing_text_item.setPlainText(text.strip())
                    else:
                        # 如果文本为空，删除该文本项
                        self.scene().removeItem(existing_text_item)
                else:
                    # 创建新文本项
                    if text.strip():
                        text_item = TextItem(text.strip(), scene_pos)
                        self.scene().addItem(text_item)

            # 重置定时器
            self.main_window.text_mode_timer.start(60000)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.main_window and self.main_window.arrow_mode:
            # 强制保持十字光标
            self.viewport().setCursor(Qt.CrossCursor)
            if self.main_window.arrow_start_point:
                # 更新临时箭头线条
                scene_pos = self.mapToScene(event.pos())
                if self.main_window.temp_arrow_line:
                    line = QLineF(self.main_window.arrow_start_point, scene_pos)
                    self.main_window.temp_arrow_line.setLine(line)
            event.accept()  # 标记事件已处理
        elif self.main_window and self.main_window.line_mode:
            # 强制保持十字光标
            self.viewport().setCursor(Qt.CrossCursor)
            if self.main_window.line_start_point:
                # 更新临时细线
                scene_pos = self.mapToScene(event.pos())
                if self.main_window.temp_line:
                    line = QLineF(self.main_window.line_start_point, scene_pos)
                    self.main_window.temp_line.setLine(line)
            event.accept()  # 标记事件已处理
        elif self.main_window and self.main_window.rect_mode:
            # 强制保持十字光标
            self.viewport().setCursor(Qt.CrossCursor)
            if self.main_window.rect_start_point:
                # 更新临时矩形
                scene_pos = self.mapToScene(event.pos())
                if self.main_window.temp_rect:
                    start = self.main_window.rect_start_point
                    x = min(start.x(), scene_pos.x())
                    y = min(start.y(), scene_pos.y())
                    width = abs(scene_pos.x() - start.x())
                    height = abs(scene_pos.y() - start.y())
                    self.main_window.temp_rect.setRect(x, y, width, height)
            event.accept()  # 标记事件已处理
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.main_window and self.main_window.arrow_mode and event.button() == Qt.LeftButton:
            if self.main_window.arrow_start_point:
                scene_pos = self.mapToScene(event.pos())

                # 移除临时线条
                if self.main_window.temp_arrow_line:
                    self.scene().removeItem(self.main_window.temp_arrow_line)
                    self.main_window.temp_arrow_line = None

                # 创建箭头（只有当起点和终点不同时）
                if (self.main_window.arrow_start_point - scene_pos).manhattanLength() > 10:
                    arrow = ArrowItem(self.main_window.arrow_start_point, scene_pos)
                    self.scene().addItem(arrow)
                    # 添加到撤销栈
                    self.main_window.drawing_undo_stack.push_add_item(self.scene(), arrow)

                self.main_window.arrow_start_point = None
            event.accept()  # 标记事件已处理
        elif self.main_window and self.main_window.line_mode and event.button() == Qt.LeftButton:
            if self.main_window.line_start_point:
                scene_pos = self.mapToScene(event.pos())

                # 移除临时线条
                if self.main_window.temp_line:
                    self.scene().removeItem(self.main_window.temp_line)
                    self.main_window.temp_line = None

                # 创建细线（只有当起点和终点不同时）
                if (self.main_window.line_start_point - scene_pos).manhattanLength() > 10:
                    line = LineItem(self.main_window.line_start_point, scene_pos)
                    self.scene().addItem(line)
                    # 添加到撤销栈
                    self.main_window.drawing_undo_stack.push_add_item(self.scene(), line)

                self.main_window.line_start_point = None
            event.accept()  # 标记事件已处理
        elif self.main_window and self.main_window.rect_mode and event.button() == Qt.LeftButton:
            if self.main_window.rect_start_point:
                scene_pos = self.mapToScene(event.pos())

                # 移除临时矩形
                if self.main_window.temp_rect:
                    self.scene().removeItem(self.main_window.temp_rect)
                    self.main_window.temp_rect = None

                # 创建矩形框（只有当起点和终点不同时）
                if (self.main_window.rect_start_point - scene_pos).manhattanLength() > 10:
                    rect = RectItem(self.main_window.rect_start_point, scene_pos)
                    self.scene().addItem(rect)
                    # 添加到撤销栈
                    self.main_window.drawing_undo_stack.push_add_item(self.scene(), rect)

                self.main_window.rect_start_point = None
            event.accept()  # 标记事件已处理
        else:
            super().mouseReleaseEvent(event)


class ImageComposer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ImageComposer", "Settings")
        self.hotkey = self.settings.value("hotkey", "ctrl+win+z")

        # 创建信号发射器用于线程安全的窗口显示/隐藏切换
        self.hotkey_emitter = HotkeySignalEmitter()
        self.hotkey_emitter.show_signal.connect(self.toggle_window)

        # 创建箭头操作的撤销栈
        self.drawing_undo_stack = DrawingUndoStack()

        # 创建快照管理器
        self.snapshot_manager = SnapshotManager()

        # 初始化音频播放器
        self.media_player = QMediaPlayer()
        self.media_player.setVolume(100)  # 设置音量为100%
        self.success_sound_path = os.path.join(os.path.dirname(__file__), "prompt_tone.mp3")
        self.ctrl_s_sound_path = os.path.join(os.path.dirname(__file__), "ctrl+s.mp3")
        self.alt_s_sound_path = os.path.join(os.path.dirname(__file__), "alt+s.mp3")

        # 标记是否是第一次显示窗口
        self.first_show = True

        self.init_ui()
        self.create_system_tray()
        self.setup_global_hotkey()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("图片合成器 - Image Composer (PyQt5)")
        self.setGeometry(100, 100, 1400, 900)

        # 设置窗口图标（任务栏图标）
        icon_path = os.path.join(os.path.dirname(__file__), "2048x2048.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 创建场景和视图
        self.scene = QGraphicsScene()
        self.scene.setSceneRect(-5000, -5000, 10000, 10000)  # 设置更大的场景，允许负坐标

        self.view = CustomGraphicsView(self.scene)
        self.view.main_window = self  # 设置对主窗口的引用
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setBackgroundBrush(Qt.white)

        # 设置滚动条策略 - 始终显示滚动条
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.setCentralWidget(self.view)

        # 工具栏可见状态（默认隐藏）
        self.toolbars_visible = False

        # 箭头绘制模式
        self.arrow_mode = False
        self.arrow_start_point = None
        self.temp_arrow_line = None

        # 箭头模式自动退出定时器（1分钟）
        self.arrow_mode_timer = QTimer()
        self.arrow_mode_timer.timeout.connect(self.auto_exit_arrow_mode)
        self.arrow_mode_timer.setSingleShot(True)  # 只触发一次

        # 画线绘制模式
        self.line_mode = False
        self.line_start_point = None
        self.temp_line = None

        # 画线模式自动退出定时器（1分钟）
        self.line_mode_timer = QTimer()
        self.line_mode_timer.timeout.connect(self.auto_exit_line_mode)
        self.line_mode_timer.setSingleShot(True)  # 只触发一次

        # 矩形绘制模式
        self.rect_mode = False
        self.rect_start_point = None
        self.temp_rect = None

        # 矩形模式自动退出定时器（1分钟）
        self.rect_mode_timer = QTimer()
        self.rect_mode_timer.timeout.connect(self.auto_exit_rect_mode)
        self.rect_mode_timer.setSingleShot(True)  # 只触发一次

        # 移动模式（框选和移动图片/形状）
        self.move_mode = False

        # 文本绘制模式
        self.text_mode = False

        # 文本模式自动退出定时器（1分钟）
        self.text_mode_timer = QTimer()
        self.text_mode_timer.timeout.connect(self.auto_exit_text_mode)
        self.text_mode_timer.setSingleShot(True)  # 只触发一次

        # 创建工具栏
        self.create_toolbar()

        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 | Ctrl+S 合并 | Ctrl+Z 撤销 | Ctrl+O 导入 | Alt+S 导出 | Ctrl+A 箭头 | Ctrl+L 线 | Ctrl+R 矩形 | Ctrl+T 文字 | Ctrl+M 移动")

        # 图片计数
        self.image_count = 0

        # 待删除的原始文件路径（用于合并后导出时删除）
        self.pending_delete_files = []

    def create_system_tray(self):
        """创建系统托盘图标"""
        # 创建托盘图标
        self.tray_icon = QSystemTrayIcon(self)

        # 尝试加载自定义图标
        icon_path = os.path.join(os.path.dirname(__file__), "2048x2048.png")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            # 如果文件不存在，使用系统默认图标
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)

        self.tray_icon.setIcon(icon)

        # 创建托盘菜单
        tray_menu = QMenu()

        # 显示/隐藏窗口
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)

        hide_action = QAction("隐藏窗口", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)

        tray_menu.addSeparator()

        # 快捷键设置
        hotkey_action = QAction("设置快捷键...", self)
        hotkey_action.triggered.connect(self.open_hotkey_settings)
        tray_menu.addAction(hotkey_action)

        tray_menu.addSeparator()

        # 退出程序
        quit_action = QAction("退出程序 (&X)", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)

        # 双击托盘图标显示窗口
        self.tray_icon.activated.connect(self.tray_icon_activated)

        # 显示托盘图标
        self.tray_icon.show()
        self.tray_icon.setToolTip("图片合成器")

    def tray_icon_activated(self, reason):
        """托盘图标被激活时的处理"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def show_window(self):
        """显示窗口"""
        if self.first_show:
            # 第一次显示时最大化
            self.showMaximized()
            self.first_show = False
        else:
            # 后续显示时使用普通显示
            self.show()
        self.activateWindow()
        self.raise_()

    def toggle_window(self):
        """切换窗口的显示/隐藏状态"""
        if self.isVisible():
            # 窗口当前可见，隐藏到托盘
            self.hide()
            self.tray_icon.showMessage(
                "图片合成器",
                "程序已最小化到系统托盘\n双击托盘图标或使用快捷键可重新打开",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            # 窗口当前隐藏，显示窗口
            self.show_window()

    def play_success_sound(self):
        """使用默认设备播放成功提示音"""
        if not os.path.exists(self.success_sound_path):
            QApplication.beep()
            return

        # 使用 QMediaPlayer 播放（默认设备）
        self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(self.success_sound_path)))
        self.media_player.play()

    def play_ctrl_s_sound(self):
        """播放 Ctrl+S 合并提示音"""
        if not os.path.exists(self.ctrl_s_sound_path):
            QApplication.beep()
            return
        self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(self.ctrl_s_sound_path)))
        self.media_player.play()

    def play_alt_s_sound(self):
        """播放 Alt+S 导出提示音"""
        if not os.path.exists(self.alt_s_sound_path):
            QApplication.beep()
            return
        self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(self.alt_s_sound_path)))
        self.media_player.play()

    def setup_global_hotkey(self):
        """设置全局快捷键"""
        if not KEYBOARD_AVAILABLE:
            return

        try:
            # 移除旧的快捷键
            keyboard.unhook_all()
            # 注册新的快捷键 - 使用信号发射器确保线程安全
            keyboard.add_hotkey(self.hotkey, lambda: self.hotkey_emitter.show_signal.emit())
        except Exception as e:
            print(f"设置全局快捷键失败: {e}")

    def open_hotkey_settings(self):
        """打开快捷键设置对话框"""
        dialog = HotkeySettingsDialog(self.hotkey, self)
        if dialog.exec_() == QDialog.Accepted:
            new_hotkey = dialog.get_hotkey()
            if new_hotkey:
                self.hotkey = new_hotkey
                self.settings.setValue("hotkey", self.hotkey)
                self.setup_global_hotkey()
                QMessageBox.information(self, "成功", f"快捷键已设置为: {self.hotkey}")

    def closeEvent(self, event):
        """关闭窗口事件 - 最小化到托盘而不是退出"""
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "图片合成器",
            "程序已最小化到系统托盘\n双击托盘图标或使用快捷键可重新打开",
            QSystemTrayIcon.Information,
            2000
        )

    def quit_application(self):
        """真正退出程序"""
        if KEYBOARD_AVAILABLE:
            keyboard.unhook_all()
        self.tray_icon.hide()
        QApplication.quit()

    def create_toolbar(self):
        """创建工具栏（分两行显示）"""
        # 第一行工具栏：文件操作
        self.toolbar1 = QToolBar("文件操作")
        self.toolbar1.setMovable(False)
        self.toolbar1.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toolbar1.setIconSize(QSize(16, 16))
        self.toolbar1.setFloatable(False)
        self.addToolBar(self.toolbar1)

        # 添加折叠/展开按钮到工具栏最左侧
        self.toggle_btn = QPushButton("▶")
        self.toggle_btn.setFixedSize(20, 20)
        self.toggle_btn.setToolTip("展开工具栏")
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                border: 1px solid #999;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #c0c0c0;
            }
        """)
        self.toggle_btn.clicked.connect(self.toggle_toolbars)
        self.toolbar1.addWidget(self.toggle_btn)

        # 导入图片
        import_action = QAction("📁 导入 (Ctrl+O)", self)
        import_action.setShortcut(QKeySequence("Ctrl+O"))
        import_action.setToolTip("导入图片 (Ctrl+O)")
        import_action.triggered.connect(self.import_images)
        self.toolbar1.addAction(import_action)
        self.addAction(import_action)  # 同时添加到主窗口，确保快捷键始终有效

        # 绑定Ctrl+Shift+O快捷键（从任意位置选择文件）
        import_anywhere_action = QAction(self)
        import_anywhere_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        import_anywhere_action.triggered.connect(self.import_images_from_anywhere)
        self.addAction(import_anywhere_action)

        # 导出图片 - Alt+S 最终保存
        export_action = QAction("💾 导出 (Alt+S)", self)
        export_action.setShortcut(QKeySequence("Alt+S"))
        export_action.setToolTip("导出图片到文件 (Alt+S)")
        export_action.triggered.connect(self.export_image)
        self.toolbar1.addAction(export_action)
        self.addAction(export_action)  # 同时添加到主窗口

        # 绑定Ctrl+Shift+S快捷键（保存到桌面）
        export_desktop_action = QAction(self)
        export_desktop_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        export_desktop_action.triggered.connect(self.export_to_desktop)
        self.addAction(export_desktop_action)

        self.toolbar1.addSeparator()

        # 删除选中
        delete_action = QAction("🗑️ 删除 (Del)", self)
        delete_action.setShortcut(QKeySequence("Delete"))
        delete_action.setToolTip("删除选中的图片 (Delete)")
        delete_action.triggered.connect(self.delete_selected)
        self.toolbar1.addAction(delete_action)
        self.addAction(delete_action)  # 同时添加到主窗口

        # 清空画布
        clear_action = QAction("🗑️ 清空 (Ctrl+Del)", self)
        clear_action.setShortcut(QKeySequence("Ctrl+Del"))
        clear_action.setToolTip("清空画布上的所有图片 (Ctrl+Del)")
        clear_action.triggered.connect(self.clear_canvas)
        self.toolbar1.addAction(clear_action)
        self.addAction(clear_action)  # 同时添加到主窗口，确保快捷键始终有效

        # 强制换行，开始第二行工具栏
        self.addToolBarBreak()

        # 第二行工具栏：编辑和视图操作
        self.toolbar2 = QToolBar("编辑操作")
        self.toolbar2.setMovable(False)
        self.toolbar2.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toolbar2.setIconSize(QSize(16, 16))
        self.toolbar2.setFloatable(False)
        self.addToolBar(self.toolbar2)

        # 画箭头模式
        self.arrow_action = QAction("➡️ 画箭头 (Ctrl+A)", self)
        self.arrow_action.setShortcut(QKeySequence("Ctrl+A"))
        self.arrow_action.setToolTip("开启/关闭箭头绘制模式 (Ctrl+A)")
        self.arrow_action.setCheckable(True)
        self.arrow_action.triggered.connect(self.toggle_arrow_mode)
        self.toolbar2.addAction(self.arrow_action)
        self.addAction(self.arrow_action)

        # 画线模式
        self.line_action = QAction("📏 画细线 (Ctrl+L)", self)
        self.line_action.setShortcut(QKeySequence("Ctrl+L"))
        self.line_action.setToolTip("开启/关闭细线绘制模式 (Ctrl+L)")
        self.line_action.setCheckable(True)
        self.line_action.triggered.connect(self.toggle_line_mode)
        self.toolbar2.addAction(self.line_action)
        self.addAction(self.line_action)

        # 画矩形模式
        self.rect_action = QAction("⬜ 画矩形 (Ctrl+R)", self)
        self.rect_action.setShortcut(QKeySequence("Ctrl+R"))
        self.rect_action.setToolTip("开启/关闭矩形绘制模式 (Ctrl+R)")
        self.rect_action.setCheckable(True)
        self.rect_action.triggered.connect(self.toggle_rect_mode)
        self.toolbar2.addAction(self.rect_action)
        self.addAction(self.rect_action)

        # 文本模式
        self.text_action = QAction("T 文本 (Ctrl+T)", self)
        self.text_action.setShortcut(QKeySequence("Ctrl+T"))
        self.text_action.setToolTip("开启/关闭文本输入模式 (Ctrl+T)")
        self.text_action.setCheckable(True)
        self.text_action.triggered.connect(self.toggle_text_mode)
        self.toolbar2.addAction(self.text_action)
        self.addAction(self.text_action)

        # 移动模式
        self.move_action = QAction("✥ 移动 (Ctrl+M)", self)
        self.move_action.setShortcut(QKeySequence("Ctrl+M"))
        self.move_action.setToolTip("开启/关闭移动模式，可框选和移动图片/形状 (Ctrl+M)")
        self.move_action.setCheckable(True)
        self.move_action.triggered.connect(self.toggle_move_mode)
        self.toolbar2.addAction(self.move_action)
        self.addAction(self.move_action)

        self.toolbar2.addSeparator()

        # 合并图层 - Ctrl+S 临时合并
        snapshot_action = QAction("📸 合并 (Ctrl+S)", self)
        snapshot_action.setShortcut(QKeySequence("Ctrl+S"))
        snapshot_action.setToolTip("合并所有内容为一张图片 (Ctrl+S)")
        snapshot_action.triggered.connect(self.save_snapshot)
        self.toolbar2.addAction(snapshot_action)
        self.addAction(snapshot_action)

        # 撤销操作
        undo_action = QAction("↶ 撤销 (Ctrl+Z)", self)
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        undo_action.setToolTip("撤销绘图操作或合并 (Ctrl+Z)")
        undo_action.triggered.connect(self.undo_snapshot)
        self.toolbar2.addAction(undo_action)
        self.addAction(undo_action)

        self.toolbar2.addSeparator()

        # 放大视图
        zoom_in_action = QAction("🔍+ 放大视图 (Ctrl+=)", self)
        zoom_in_action.setShortcut(QKeySequence("Ctrl+="))
        zoom_in_action.setToolTip("放大视图，像素不变 (Ctrl+=)")
        zoom_in_action.triggered.connect(self.zoom_view_in)
        self.toolbar2.addAction(zoom_in_action)
        self.addAction(zoom_in_action)  # 同时添加到主窗口

        # 缩小视图
        zoom_out_action = QAction("🔍- 缩小视图 (Ctrl+-)", self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.setToolTip("缩小视图 (Ctrl+-)")
        zoom_out_action.triggered.connect(self.zoom_view_out)
        self.toolbar2.addAction(zoom_out_action)
        self.addAction(zoom_out_action)  # 同时添加到主窗口

        # 重置视图
        reset_size_action = QAction("↺ 重置视图 (Ctrl+0)", self)
        reset_size_action.setShortcut(QKeySequence("Ctrl+0"))
        reset_size_action.setToolTip("重置视图缩放 (Ctrl+0)")
        reset_size_action.triggered.connect(self.reset_view_zoom)
        self.toolbar2.addAction(reset_size_action)
        self.addAction(reset_size_action)  # 同时添加到主窗口

        self.toolbar2.addSeparator()

        # 适应窗口
        fit_action = QAction("🖼️ 适应窗口 (Ctrl+P)", self)
        fit_action.setShortcut(QKeySequence("Ctrl+P"))
        fit_action.setToolTip("调整视图以显示所有图片 (Ctrl+P)")
        fit_action.triggered.connect(self.fit_in_view)
        self.toolbar2.addAction(fit_action)
        self.addAction(fit_action)  # 同时添加到主窗口

        # 重置视图
        reset_action = QAction("🔄 重置视图", self)
        reset_action.setToolTip("重置视图缩放和位置")
        reset_action.triggered.connect(self.reset_view)
        self.toolbar2.addAction(reset_action)

        # 根据初始状态设置工具栏显示
        if not self.toolbars_visible:
            # 完全隐藏工具栏，只显示切换按钮
            self.toolbar1.setMaximumHeight(30)  # 限制高度只显示按钮

            # 只隐藏widget，不隐藏action（这样快捷键依然有效）
            for i in range(self.toolbar1.layout().count()):
                item = self.toolbar1.layout().itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if widget != self.toggle_btn:
                        widget.setVisible(False)

            self.toolbar2.hide()

    def toggle_toolbars(self):
        """切换工具栏的显示/隐藏状态"""
        self.toolbars_visible = not self.toolbars_visible

        if self.toolbars_visible:
            # 展开工具栏
            self.toolbar1.setMaximumHeight(16777215)  # 恢复默认最大高度

            # 显示所有widget
            for i in range(self.toolbar1.layout().count()):
                item = self.toolbar1.layout().itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    widget.setVisible(True)

            self.toolbar2.show()
            self.toggle_btn.setText("◀")
            self.toggle_btn.setToolTip("隐藏工具栏")
        else:
            # 完全隐藏工具栏，只显示切换按钮
            self.toolbar1.setMaximumHeight(30)  # 限制高度只显示按钮

            # 只隐藏widget，不隐藏action（这样快捷键依然有效）
            for i in range(self.toolbar1.layout().count()):
                item = self.toolbar1.layout().itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if widget != self.toggle_btn:
                        widget.setVisible(False)

            self.toolbar2.hide()
            self.toggle_btn.setText("▶")
            self.toggle_btn.setToolTip("展开工具栏")

    def import_images(self):
        """导入多张图片"""
        # 从环境变量获取输入目录
        default_path = INPUT_DIR
        # 如果目录不存在，回退到用户主目录
        if not os.path.exists(default_path):
            default_path = os.path.expanduser("~")

        # 使用自定义图片选择器
        picker = CustomImagePicker(default_path, self)
        if picker.exec_() != QDialog.Accepted:
            return

        file_paths = picker.get_selected_files()
        if not file_paths:
            return

        # 起始位置
        offset_x = 100
        offset_y = 100

        for i, file_path in enumerate(file_paths):
            try:
                # 使用PIL加载原始图片
                pil_image = Image.open(file_path)

                # 直接使用原始图片，不进行缩放
                display_image = pil_image

                # 转换为QPixmap
                pixmap = self.pil_to_qpixmap(display_image)

                # 创建可拖拽的图片项（display_scale=1.0表示不缩放，传递文件路径）
                item = DraggablePixmapItem(pixmap, pil_image, display_scale=1.0, file_path=file_path)

                # 设置位置（每张图片稍微错开）
                x = offset_x + (i * 40)
                y = offset_y + (i * 40)
                item.setPos(x, y)

                # 添加到场景
                self.scene.addItem(item)
                self.image_count += 1

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "错误",
                    f"无法加载图片 {os.path.basename(file_path)}:\n{str(e)}"
                )

        # 更新场景矩形以适应导入的图片
        self.update_scene_rect()
        self.status_bar.showMessage(f"已导入 {len(file_paths)} 张图片，画布共有 {self.image_count} 张图片")

    def import_images_from_anywhere(self):
        """从任意位置选择并导入图片 (Ctrl+Shift+O)"""
        # 使用标准文件选择对话框
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            os.path.expanduser("~"),
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)"
        )

        if not file_paths:
            return

        # 起始位置
        offset_x = 100
        offset_y = 100

        for i, file_path in enumerate(file_paths):
            try:
                # 使用PIL加载原始图片
                pil_image = Image.open(file_path)

                # 直接使用原始图片，不进行缩放
                display_image = pil_image

                # 转换为QPixmap
                pixmap = self.pil_to_qpixmap(display_image)

                # 创建可拖拽的图片项（display_scale=1.0表示不缩放，传递文件路径）
                item = DraggablePixmapItem(pixmap, pil_image, display_scale=1.0, file_path=file_path)

                # 设置位置（每张图片稍微错开）
                x = offset_x + (i * 40)
                y = offset_y + (i * 40)
                item.setPos(x, y)

                # 添加到场景
                self.scene.addItem(item)
                self.image_count += 1

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "错误",
                    f"无法加载图片 {os.path.basename(file_path)}:\n{str(e)}"
                )

        # 更新场景矩形以适应导入的图片
        self.update_scene_rect()
        self.status_bar.showMessage(f"已导入 {len(file_paths)} 张图片，画布共有 {self.image_count} 张图片")

    def import_recent_images(self, count):
        """自动导入最近的N张图片（不打开对话框）"""
        # 从环境变量获取输入目录
        default_path = INPUT_DIR

        # 如果目录不存在，显示错误信息
        if not os.path.exists(default_path):
            self.status_bar.showMessage(f"目录不存在: {default_path}")
            QApplication.beep()
            return

        # 支持的图片格式
        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')

        # 获取所有图片文件及其创建时间
        files_with_time = []
        for filename in os.listdir(default_path):
            if filename.lower().endswith(image_extensions):
                file_path = os.path.join(default_path, filename)
                try:
                    # 获取文件创建时间
                    create_time = os.path.getctime(file_path)
                    files_with_time.append((file_path, create_time))
                except Exception:
                    continue

        # 按创建时间从新到旧排序（时间大的在前）
        files_with_time.sort(key=lambda x: x[1], reverse=True)

        # 只取前N张图片
        files_with_time = files_with_time[:count]

        if not files_with_time:
            self.status_bar.showMessage(f"在 {default_path} 中没有找到图片")
            QApplication.beep()
            return

        # 起始位置
        offset_x = 100
        offset_y = 100

        imported_count = 0
        for i, (file_path, _) in enumerate(files_with_time):
            try:
                # 使用PIL加载原始图片
                pil_image = Image.open(file_path)

                # 直接使用原始图片，不进行缩放
                display_image = pil_image

                # 转换为QPixmap
                pixmap = self.pil_to_qpixmap(display_image)

                # 创建可拖拽的图片项（display_scale=1.0表示不缩放，传递文件路径）
                item = DraggablePixmapItem(pixmap, pil_image, display_scale=1.0, file_path=file_path)

                # 设置位置（每张图片稍微错开）
                x = offset_x + (i * 40)
                y = offset_y + (i * 40)
                item.setPos(x, y)

                # 添加到场景
                self.scene.addItem(item)
                self.image_count += 1
                imported_count += 1

            except Exception as e:
                print(f"无法加载图片 {os.path.basename(file_path)}: {str(e)}")
                continue

        # 更新场景矩形以适应导入的图片
        self.update_scene_rect()

        # 导入成功后播放音效
        if imported_count > 0:
            self.play_ctrl_s_sound()

        self.status_bar.showMessage(f"已自动导入最近的 {imported_count} 张图片，画布共有 {self.image_count} 张图片")

    def pil_to_qpixmap(self, pil_image):
        """将PIL图片转换为QPixmap"""
        # 转换为RGBA模式
        if pil_image.mode != 'RGBA':
            pil_image = pil_image.convert('RGBA')

        # 获取图片数据
        data = pil_image.tobytes('raw', 'RGBA')

        # 创建QImage
        qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGBA8888)

        # 转换为QPixmap
        return QPixmap.fromImage(qimage)

    def set_items_interactive(self, interactive):
        """设置场景交互性

        在绘图模式下禁用场景交互，防止鼠标事件被项目拦截
        """
        # 使用 view.setInteractive 来完全禁用/启用场景交互
        self.view.setInteractive(interactive)

    def update_scene_rect(self):
        """更新场景矩形以适应所有项目，并添加边距"""
        items_rect = self.scene.itemsBoundingRect()
        if not items_rect.isEmpty():
            # 添加边距，确保放大后有足够空间
            margin = 2000
            expanded_rect = items_rect.adjusted(-margin, -margin, margin, margin)
            self.scene.setSceneRect(expanded_rect)

    def toggle_arrow_mode(self):
        """切换箭头绘制模式"""
        # 如果已经在箭头模式，保持模式并重置计时器
        if self.arrow_mode:
            self.arrow_action.setChecked(True)
            self.arrow_mode_timer.start(60000)
            self.status_bar.showMessage("箭头绘制模式：按住鼠标左键拖动绘制箭头 | 1分钟无操作自动退出")
            return

        self.arrow_mode = self.arrow_action.isChecked()

        if self.arrow_mode:
            # 进入箭头模式，先退出其他模式
            if self.line_mode:
                self.line_mode = False
                self.line_action.setChecked(False)
                self.toggle_line_mode()
            if self.rect_mode:
                self.rect_mode = False
                self.rect_action.setChecked(False)
                self.toggle_rect_mode()
            if self.text_mode:
                self.text_mode = False
                self.text_action.setChecked(False)
                self.toggle_text_mode()
            if self.move_mode:
                self.move_mode = False
                self.move_action.setChecked(False)
                self.toggle_move_mode()

            # 禁用图片交互，防止鼠标事件被拦截
            self.set_items_interactive(False)

            # 先设置为NoDrag模式，再设置光标
            self.view.setDragMode(QGraphicsView.NoDrag)
            # 强制设置视图和视口的光标为十字光标
            self.view.setCursor(Qt.CrossCursor)
            self.view.viewport().setCursor(Qt.CrossCursor)
            self.view.viewport().setMouseTracking(True)
            self.status_bar.showMessage("箭头绘制模式：按住鼠标左键拖动绘制箭头 | 1分钟无操作自动退出")
            # 启动1分钟定时器
            self.arrow_mode_timer.start(60000)  # 60000毫秒 = 1分钟
        else:
            # 退出箭头模式
            self.set_items_interactive(True)  # 恢复图片交互
            self.view.setDragMode(QGraphicsView.ScrollHandDrag)
            self.view.setCursor(Qt.ArrowCursor)
            self.view.viewport().setCursor(Qt.ArrowCursor)
            self.status_bar.showMessage("已退出箭头绘制模式")

            # 停止定时器
            self.arrow_mode_timer.stop()

            # 清理未完成的临时线条
            if self.temp_arrow_line:
                self.scene.removeItem(self.temp_arrow_line)
                self.temp_arrow_line = None
            self.arrow_start_point = None

    def auto_exit_arrow_mode(self):
        """1分钟无操作后自动退出箭头模式"""
        if self.arrow_mode:
            # 先将模式变量设为False，再调用toggle退出
            self.arrow_mode = False
            self.arrow_action.setChecked(False)
            self.toggle_arrow_mode()
            self.status_bar.showMessage("箭头绘制模式已自动退出（1分钟无操作）")

    def toggle_line_mode(self):
        """切换细线绘制模式"""
        # 如果已经在细线模式，保持模式并重置计时器
        if self.line_mode:
            self.line_action.setChecked(True)
            self.line_mode_timer.start(60000)
            self.status_bar.showMessage("细线绘制模式：按住鼠标左键拖动绘制细线 | 1分钟无操作自动退出")
            return

        self.line_mode = self.line_action.isChecked()

        if self.line_mode:
            # 进入画线模式，先退出其他模式
            if self.arrow_mode:
                self.arrow_mode = False
                self.arrow_action.setChecked(False)
                self.toggle_arrow_mode()
            if self.rect_mode:
                self.rect_mode = False
                self.rect_action.setChecked(False)
                self.toggle_rect_mode()
            if self.text_mode:
                self.text_mode = False
                self.text_action.setChecked(False)
                self.toggle_text_mode()
            if self.move_mode:
                self.move_mode = False
                self.move_action.setChecked(False)
                self.toggle_move_mode()

            # 禁用图片交互，防止鼠标事件被拦截
            self.set_items_interactive(False)

            # 先设置为NoDrag模式，再设置光标
            self.view.setDragMode(QGraphicsView.NoDrag)
            # 强制设置视图和视口的光标为十字光标
            self.view.setCursor(Qt.CrossCursor)
            self.view.viewport().setCursor(Qt.CrossCursor)
            self.view.viewport().setMouseTracking(True)
            self.status_bar.showMessage("细线绘制模式：按住鼠标左键拖动绘制细线 | 1分钟无操作自动退出")
            # 启动1分钟定时器
            self.line_mode_timer.start(60000)  # 60000毫秒 = 1分钟
        else:
            # 退出画线模式
            self.set_items_interactive(True)  # 恢复图片交互
            self.view.setDragMode(QGraphicsView.ScrollHandDrag)
            self.view.setCursor(Qt.ArrowCursor)
            self.view.viewport().setCursor(Qt.ArrowCursor)
            self.status_bar.showMessage("已退出细线绘制模式")

            # 停止定时器
            self.line_mode_timer.stop()

            # 清理未完成的临时线条
            if self.temp_line:
                self.scene.removeItem(self.temp_line)
                self.temp_line = None
            self.line_start_point = None

    def auto_exit_line_mode(self):
        """1分钟无操作后自动退出画线模式"""
        if self.line_mode:
            # 先将模式变量设为False，再调用toggle退出
            self.line_mode = False
            self.line_action.setChecked(False)
            self.toggle_line_mode()
            self.status_bar.showMessage("细线绘制模式已自动退出（1分钟无操作）")

    def toggle_rect_mode(self):
        """切换矩形绘制模式"""
        # 如果已经在矩形模式，保持模式并重置计时器
        if self.rect_mode:
            self.rect_action.setChecked(True)
            self.rect_mode_timer.start(60000)
            self.status_bar.showMessage("矩形绘制模式：按住鼠标左键拖动绘制矩形框 | 1分钟无操作自动退出")
            return

        self.rect_mode = self.rect_action.isChecked()

        if self.rect_mode:
            # 进入矩形模式，先退出其他模式
            if self.arrow_mode:
                self.arrow_mode = False
                self.arrow_action.setChecked(False)
                self.toggle_arrow_mode()
            if self.line_mode:
                self.line_mode = False
                self.line_action.setChecked(False)
                self.toggle_line_mode()
            if self.text_mode:
                self.text_mode = False
                self.text_action.setChecked(False)
                self.toggle_text_mode()
            if self.move_mode:
                self.move_mode = False
                self.move_action.setChecked(False)
                self.toggle_move_mode()

            # 禁用图片交互，防止鼠标事件被拦截
            self.set_items_interactive(False)

            # 先设置为NoDrag模式，再设置光标
            self.view.setDragMode(QGraphicsView.NoDrag)
            # 强制设置视图和视口的光标为十字光标
            self.view.setCursor(Qt.CrossCursor)
            self.view.viewport().setCursor(Qt.CrossCursor)
            self.view.viewport().setMouseTracking(True)
            self.status_bar.showMessage("矩形绘制模式：按住鼠标左键拖动绘制矩形框 | 1分钟无操作自动退出")
            self.play_ctrl_s_sound()
            # 启动1分钟定时器
            self.rect_mode_timer.start(60000)  # 60000毫秒 = 1分钟
        else:
            # 退出矩形模式
            self.set_items_interactive(True)  # 恢复图片交互
            self.view.setDragMode(QGraphicsView.ScrollHandDrag)
            self.view.setCursor(Qt.ArrowCursor)
            self.view.viewport().setCursor(Qt.ArrowCursor)
            self.status_bar.showMessage("已退出矩形绘制模式")

            # 停止定时器
            self.rect_mode_timer.stop()

            # 清理未完成的临时矩形
            if self.temp_rect:
                self.scene.removeItem(self.temp_rect)
                self.temp_rect = None
            self.rect_start_point = None

    def auto_exit_rect_mode(self):
        """1分钟无操作后自动退出矩形模式"""
        if self.rect_mode:
            # 先将模式变量设为False，再调用toggle退出
            self.rect_mode = False
            self.rect_action.setChecked(False)
            self.toggle_rect_mode()
            self.status_bar.showMessage("矩形绘制模式已自动退出（1分钟无操作）")

    def toggle_text_mode(self):
        """切换文本输入模式"""
        # 如果已经在文本模式，保持模式并重置计时器
        if self.text_mode:
            self.text_action.setChecked(True)
            self.text_mode_timer.start(60000)
            self.status_bar.showMessage("文本输入模式：点击画布添加文字 | 1分钟无操作自动退出")
            return

        self.text_mode = self.text_action.isChecked()

        if self.text_mode:
            # 进入文本模式，先退出其他模式
            if self.arrow_mode:
                self.arrow_mode = False
                self.arrow_action.setChecked(False)
                self.toggle_arrow_mode()
            if self.line_mode:
                self.line_mode = False
                self.line_action.setChecked(False)
                self.toggle_line_mode()
            if self.rect_mode:
                self.rect_mode = False
                self.rect_action.setChecked(False)
                self.toggle_rect_mode()
            if self.move_mode:
                self.move_mode = False
                self.move_action.setChecked(False)
                self.toggle_move_mode()

            # 禁用图片交互，防止鼠标事件被拦截
            self.set_items_interactive(False)

            # 先设置为NoDrag模式，再设置光标
            self.view.setDragMode(QGraphicsView.NoDrag)
            # 强制设置视图和视口的光标为十字光标
            self.view.setCursor(Qt.CrossCursor)
            self.view.viewport().setCursor(Qt.CrossCursor)
            self.view.viewport().setMouseTracking(True)
            self.status_bar.showMessage("文本输入模式：点击画布添加文字 | 1分钟无操作自动退出")
            # 启动1分钟定时器
            self.text_mode_timer.start(60000)
        else:
            # 退出文本模式
            self.set_items_interactive(True)  # 恢复图片交互
            self.view.setDragMode(QGraphicsView.ScrollHandDrag)
            self.view.setCursor(Qt.ArrowCursor)
            self.view.viewport().setCursor(Qt.ArrowCursor)
            self.status_bar.showMessage("已退出文本输入模式")

            # 停止定时器
            self.text_mode_timer.stop()

    def auto_exit_text_mode(self):
        """1分钟无操作后自动退出文本模式"""
        if self.text_mode:
            # 先将模式变量设为False，再调用toggle退出
            self.text_mode = False
            self.text_action.setChecked(False)
            self.toggle_text_mode()
            self.status_bar.showMessage("文本输入模式已自动退出（1分钟无操作）")

    def toggle_move_mode(self):
        """切换移动模式"""
        # 如果已经在移动模式，保持模式
        if self.move_mode:
            self.move_action.setChecked(True)
            self.status_bar.showMessage("移动模式：可框选和移动图片/形状/文字")
            return

        self.move_mode = self.move_action.isChecked()

        if self.move_mode:
            # 进入移动模式，先退出其他绘制模式
            if self.arrow_mode:
                self.arrow_mode = False
                self.arrow_action.setChecked(False)
                self.toggle_arrow_mode()
            if self.line_mode:
                self.line_mode = False
                self.line_action.setChecked(False)
                self.toggle_line_mode()
            if self.rect_mode:
                self.rect_mode = False
                self.rect_action.setChecked(False)
                self.toggle_rect_mode()
            if self.text_mode:
                self.text_mode = False
                self.text_action.setChecked(False)
                self.toggle_text_mode()

            # 设置为橡皮筋选择模式（可框选多个项目）
            self.view.setDragMode(QGraphicsView.RubberBandDrag)
            self.view.setCursor(Qt.ArrowCursor)
            self.view.viewport().setCursor(Qt.ArrowCursor)
            self.status_bar.showMessage("移动模式：可框选和移动图片/形状/文字")
        else:
            # 退出移动模式，恢复默认的拖拽画布模式
            self.view.setDragMode(QGraphicsView.ScrollHandDrag)
            self.view.setCursor(Qt.ArrowCursor)
            self.view.viewport().setCursor(Qt.ArrowCursor)
            self.status_bar.showMessage("已退出移动模式")

    def save_snapshot(self):
        """合并当前画布内容为一张图片 (Ctrl+S) - 保持当前显示状态完全不变"""
        all_items = self.scene.items()
        if not all_items:
            self.status_bar.showMessage("画布为空，无法合并")
            return

        # 先保存当前状态到快照（用于撤销）
        count = self.snapshot_manager.save_snapshot(self.scene, None)

        # 获取当前显示状态的边界框
        display_rect = self.scene.itemsBoundingRect()
        if display_rect.isEmpty():
            self.status_bar.showMessage("画布为空，无法合并")
            return

        # 直接用当前显示状态渲染（不改变任何缩放）
        width = int(display_rect.width())
        height = int(display_rect.height())

        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.white)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self.scene.render(painter, QRectF(0, 0, width, height), display_rect)
        painter.end()

        # 收集所有原始图片的文件路径（用于导出时删除）
        for item in all_items:
            if isinstance(item, DraggablePixmapItem):
                if item.file_path and item.file_path not in self.pending_delete_files:
                    self.pending_delete_files.append(item.file_path)

        # 清空场景
        self.scene.clear()

        # 创建合并后的图片，位置与原来完全一致
        pixmap = QPixmap.fromImage(image)
        merged_item = DraggablePixmapItem(pixmap, image, file_path=None)
        merged_item.setPos(display_rect.topLeft())
        self.scene.addItem(merged_item)

        # 更新场景矩形
        self.update_scene_rect()

        self.image_count = 1
        self.play_ctrl_s_sound()
        self.status_bar.showMessage(f"✓ 已合并 ({width}x{height} 像素) | 按 Ctrl+Z 可撤销")

    def undo_snapshot(self):
        """撤销操作 (Ctrl+Z) - 优先撤销绘图操作，没有时才撤销快照"""
        # 首先检查是否有绘图操作可撤销
        if self.drawing_undo_stack.can_undo():
            if self.drawing_undo_stack.undo():
                self.play_success_sound()
                remaining = len(self.drawing_undo_stack.undo_stack)
                self.status_bar.showMessage(f"✓ 已撤销绘图操作 | 剩余 {remaining} 个绘图操作可撤销")
                return

        # 没有绘图操作可撤销，尝试撤销快照
        if not self.snapshot_manager.has_snapshots():
            self.status_bar.showMessage("没有可撤销的操作")
            return

        success, remaining = self.snapshot_manager.restore_snapshot(self.scene)
        if success:
            self.play_success_sound()
            self.status_bar.showMessage(f"✓ 已撤销到合并前的状态 | 剩余 {remaining} 个可撤销状态")
        else:
            self.status_bar.showMessage("没有更多可撤销的操作")

    def delete_selected(self):
        """删除选中的图片、箭头、线条、矩形框或文字"""
        selected_items = self.scene.selectedItems()

        if not selected_items:
            self.status_bar.showMessage("没有选中的项目")
            return

        image_count = 0
        arrow_count = 0
        line_count = 0
        rect_count = 0
        text_count = 0
        arrows_to_delete = []
        lines_to_delete = []
        rects_to_delete = []
        texts_to_delete = []

        for item in selected_items:
            if isinstance(item, DraggablePixmapItem):
                image_count += 1
                self.image_count -= 1
                self.scene.removeItem(item)
            elif isinstance(item, ArrowItem):
                arrow_count += 1
                arrows_to_delete.append(item)
                self.scene.removeItem(item)
            elif isinstance(item, LineItem):
                line_count += 1
                lines_to_delete.append(item)
                self.scene.removeItem(item)
            elif isinstance(item, RectItem):
                rect_count += 1
                rects_to_delete.append(item)
                self.scene.removeItem(item)
            elif isinstance(item, TextItem):
                text_count += 1
                texts_to_delete.append(item)
                self.scene.removeItem(item)

        # 将箭头删除操作添加到撤销栈
        if arrows_to_delete:
            self.drawing_undo_stack.push_delete_items(self.scene, arrows_to_delete)

        # 将线条删除操作添加到撤销栈
        if lines_to_delete:
            self.drawing_undo_stack.push_delete_items(self.scene, lines_to_delete)

        # 将矩形框删除操作添加到撤销栈
        if rects_to_delete:
            self.drawing_undo_stack.push_delete_items(self.scene, rects_to_delete)

        # 将文字删除操作添加到撤销栈
        if texts_to_delete:
            self.drawing_undo_stack.push_delete_items(self.scene, texts_to_delete)

        msg = []
        if image_count > 0:
            msg.append(f"{image_count} 张图片")
        if arrow_count > 0:
            msg.append(f"{arrow_count} 个箭头")
        if line_count > 0:
            msg.append(f"{line_count} 条线")
        if rect_count > 0:
            msg.append(f"{rect_count} 个矩形框")
        if text_count > 0:
            msg.append(f"{text_count} 个文字")

        self.status_bar.showMessage(f"已删除 {' 和 '.join(msg)}" if msg else "已删除项目")

    def zoom_in_selected(self):
        """放大选中的图片"""
        selected_items = [item for item in self.scene.selectedItems()
                         if isinstance(item, DraggablePixmapItem)]

        if not selected_items:
            self.status_bar.showMessage("请先选中要放大的图片")
            return

        for item in selected_items:
            item.scale_by(1.1)

        # 更新场景矩形以适应放大后的图片
        self.update_scene_rect()
        self.status_bar.showMessage(f"已放大 {len(selected_items)} 张图片")

    def zoom_out_selected(self):
        """缩小选中的图片"""
        selected_items = [item for item in self.scene.selectedItems()
                         if isinstance(item, DraggablePixmapItem)]

        if not selected_items:
            self.status_bar.showMessage("请先选中要缩小的图片")
            return

        for item in selected_items:
            item.scale_by(0.9)

        # 更新场景矩形
        self.update_scene_rect()
        self.status_bar.showMessage(f"已缩小 {len(selected_items)} 张图片")

    def reset_selected_size(self):
        """重置选中图片的大小"""
        selected_items = [item for item in self.scene.selectedItems()
                         if isinstance(item, DraggablePixmapItem)]

        if not selected_items:
            self.status_bar.showMessage("请先选中要重置的图片")
            return

        for item in selected_items:
            item.user_scale = 1.0
            item.setScale(1.0)

        self.status_bar.showMessage(f"已重置 {len(selected_items)} 张图片的大小")

    def clear_canvas(self):
        """清空画布"""
        self.scene.clear()
        self.image_count = 0
        self.status_bar.showMessage("画布已清空")

    def fit_in_view(self):
        """适应窗口显示所有内容"""
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)

    def reset_view(self):
        """重置视图"""
        self.view.resetTransform()
        self.view.centerOn(0, 0)

    def export_image(self):
        """导出合成后的图片（自动保存到指定路径）"""
        all_items = self.scene.items()

        # 检查是否有图片、箭头、线条或矩形框
        has_content = any(isinstance(item, (DraggablePixmapItem, ArrowItem, LineItem, RectItem, TextItem)) for item in all_items)

        if not has_content:
            # 播放错误提示音
            QApplication.beep()
            self.status_bar.showMessage("画布上没有内容可导出！")
            return

        try:
            # 从环境变量获取保存目录
            save_dir = INPUT_DIR

            # 如果目录不存在，创建它
            os.makedirs(save_dir, exist_ok=True)

            # 生成时间戳文件名（使用 JPEG 格式以减小文件大小）
            timestamp = datetime.now().strftime("%Y-%m-%d %H %M %S")
            file_path = os.path.join(save_dir, f"{timestamp}.jpg")

            # 获取当前显示状态的边界框
            display_rect = self.scene.itemsBoundingRect()

            # 计算原始像素尺寸（临时将所有图片 scale 设为 1.0）
            saved_scales = {}
            for item in all_items:
                if isinstance(item, DraggablePixmapItem):
                    saved_scales[item] = item.scale()
                    item.setScale(1.0)

            original_rect = self.scene.itemsBoundingRect()

            # 恢复所有图片的 scale
            for item, scale in saved_scales.items():
                item.setScale(scale)

            # 计算缩放因子
            if original_rect.width() > 0:
                scale_factor = display_rect.width() / original_rect.width()
            else:
                scale_factor = 1.0

            # 使用显示尺寸渲染（保持所有图形位置正确）
            display_width = int(display_rect.width())
            display_height = int(display_rect.height())

            # 使用 RGB 格式（JPEG 不支持透明通道）
            image = QImage(display_width, display_height, QImage.Format_RGB32)
            image.fill(Qt.white)

            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            self.scene.render(painter, QRectF(0, 0, display_width, display_height), display_rect)
            painter.end()

            # 设置最大像素尺寸限制（宽或高不超过 1920 像素）
            MAX_SIZE = 1920
            current_width = image.width()
            current_height = image.height()

            # 如果图片超过最大尺寸，按比例缩小
            if current_width > MAX_SIZE or current_height > MAX_SIZE:
                if current_width > current_height:
                    target_width = MAX_SIZE
                    target_height = int(current_height * MAX_SIZE / current_width)
                else:
                    target_height = MAX_SIZE
                    target_width = int(current_width * MAX_SIZE / current_height)
                image = image.scaled(target_width, target_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # 保存为 JPEG 格式，质量 85%
            image.save(file_path, 'JPEG', 85)

            # 播放 Alt+S 导出提示音
            self.play_alt_s_sound()

            # 更新状态栏，显示完整路径和实际尺寸
            final_width = image.width()
            final_height = image.height()
            self.status_bar.showMessage(f"已保存到: {file_path} ({final_width}x{final_height})")

            # 导出成功后，删除画布中的所有图片和形状，并删除源文件
            deleted_files = []
            failed_deletions = []
            shape_count = 0

            for item in list(all_items):  # 使用list()创建副本，避免在迭代时修改
                if isinstance(item, DraggablePixmapItem):
                    # 尝试删除源文件
                    if item.file_path and os.path.exists(item.file_path):
                        try:
                            os.remove(item.file_path)
                            deleted_files.append(os.path.basename(item.file_path))
                        except Exception as e:
                            failed_deletions.append(f"{os.path.basename(item.file_path)}: {str(e)}")

                    # 从场景中删除图片
                    self.scene.removeItem(item)
                    self.image_count -= 1
                elif isinstance(item, (ArrowItem, LineItem, RectItem, TextItem)):
                    # 删除所有形状（箭头、线条、矩形框）
                    self.scene.removeItem(item)
                    shape_count += 1

            # 删除合并前保存的原始文件（pending_delete_files）
            for pending_file in self.pending_delete_files:
                if os.path.exists(pending_file):
                    try:
                        os.remove(pending_file)
                        deleted_files.append(os.path.basename(pending_file))
                    except Exception as e:
                        failed_deletions.append(f"{os.path.basename(pending_file)}: {str(e)}")
            self.pending_delete_files.clear()

            # 清空撤销栈（因为所有形状都被删除了）
            self.drawing_undo_stack.clear()

            # 更新状态栏消息，包含删除信息
            status_msg = f"已保存到: {file_path} ({final_width}x{final_height})"
            if deleted_files:
                status_msg += f" | 已删除 {len(deleted_files)} 个源文件"
            if shape_count > 0:
                status_msg += f" | 已清除 {shape_count} 个形状"
            if failed_deletions:
                status_msg += f" | {len(failed_deletions)} 个文件删除失败"

            self.status_bar.showMessage(status_msg)

        except Exception as e:
            # 播放错误提示音
            QApplication.beep()
            self.status_bar.showMessage(f"导出失败: {str(e)}")

    def export_to_desktop(self):
        """导出合成后的图片到桌面（不删除源文件和画布内容）"""
        all_items = self.scene.items()

        # 检查是否有图片、箭头、线条或矩形框
        has_content = any(isinstance(item, (DraggablePixmapItem, ArrowItem, LineItem, RectItem, TextItem)) for item in all_items)

        if not has_content:
            # 播放错误提示音
            QApplication.beep()
            self.status_bar.showMessage("画布上没有内容可导出！")
            return

        try:
            # 从环境变量获取桌面路径
            desktop_path = DESKTOP_DIR

            # 如果目录不存在，创建它
            os.makedirs(desktop_path, exist_ok=True)

            # 生成时间戳文件名（使用 JPEG 格式以减小文件大小）
            timestamp = datetime.now().strftime("%Y-%m-%d %H %M %S")
            file_path = os.path.join(desktop_path, f"{timestamp}.jpg")

            # 获取当前显示状态的边界框
            display_rect = self.scene.itemsBoundingRect()

            # 计算原始像素尺寸（临时将所有图片 scale 设为 1.0）
            saved_scales = {}
            for item in all_items:
                if isinstance(item, DraggablePixmapItem):
                    saved_scales[item] = item.scale()
                    item.setScale(1.0)

            original_rect = self.scene.itemsBoundingRect()

            # 恢复所有图片的 scale
            for item, scale in saved_scales.items():
                item.setScale(scale)

            # 计算缩放因子
            if original_rect.width() > 0:
                scale_factor = display_rect.width() / original_rect.width()
            else:
                scale_factor = 1.0

            # 使用显示尺寸渲染（保持所有图形位置正确）
            display_width = int(display_rect.width())
            display_height = int(display_rect.height())

            # 使用 RGB 格式（JPEG 不支持透明通道）
            image = QImage(display_width, display_height, QImage.Format_RGB32)
            image.fill(Qt.white)

            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            self.scene.render(painter, QRectF(0, 0, display_width, display_height), display_rect)
            painter.end()

            # 设置最大像素尺寸限制（宽或高不超过 1920 像素）
            MAX_SIZE = 1920
            current_width = image.width()
            current_height = image.height()

            # 如果图片超过最大尺寸，按比例缩小
            if current_width > MAX_SIZE or current_height > MAX_SIZE:
                if current_width > current_height:
                    target_width = MAX_SIZE
                    target_height = int(current_height * MAX_SIZE / current_width)
                else:
                    target_height = MAX_SIZE
                    target_width = int(current_width * MAX_SIZE / current_height)
                image = image.scaled(target_width, target_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # 保存为 JPEG 格式，质量 85%
            image.save(file_path, 'JPEG', 85)

            # 播放 Alt+S 导出提示音
            self.play_alt_s_sound()

            # 更新状态栏，显示完整路径和实际尺寸
            final_width = image.width()
            final_height = image.height()

            # 导出成功后，删除画布中的所有图片和形状，并删除源文件
            deleted_files = []
            failed_deletions = []
            shape_count = 0

            for item in list(all_items):  # 使用list()创建副本，避免在迭代时修改
                if isinstance(item, DraggablePixmapItem):
                    # 尝试删除源文件
                    if item.file_path and os.path.exists(item.file_path):
                        try:
                            os.remove(item.file_path)
                            deleted_files.append(os.path.basename(item.file_path))
                        except Exception as e:
                            failed_deletions.append(f"{os.path.basename(item.file_path)}: {str(e)}")

                    # 从场景中删除图片
                    self.scene.removeItem(item)
                    self.image_count -= 1
                elif isinstance(item, (ArrowItem, LineItem, RectItem, TextItem)):
                    # 删除所有形状（箭头、线条、矩形框）
                    self.scene.removeItem(item)
                    shape_count += 1

            # 删除合并前保存的原始文件（pending_delete_files）
            for pending_file in self.pending_delete_files:
                if os.path.exists(pending_file):
                    try:
                        os.remove(pending_file)
                        deleted_files.append(os.path.basename(pending_file))
                    except Exception as e:
                        failed_deletions.append(f"{os.path.basename(pending_file)}: {str(e)}")
            self.pending_delete_files.clear()

            # 清空撤销栈（因为所有形状都被删除了）
            self.drawing_undo_stack.clear()

            # 更新状态栏消息，包含删除信息
            status_msg = f"已保存到桌面: {file_path} ({final_width}x{final_height})"
            if deleted_files:
                status_msg += f" | 已删除 {len(deleted_files)} 个源文件"
            if shape_count > 0:
                status_msg += f" | 已清除 {shape_count} 个形状"
            if failed_deletions:
                status_msg += f" | {len(failed_deletions)} 个文件删除失败"

            self.status_bar.showMessage(status_msg)

        except Exception as e:
            # 播放错误提示音
            QApplication.beep()
            self.status_bar.showMessage(f"导出到桌面失败: {str(e)}")

    def increase_text_font_size(self):
        """放大选中文字的字体"""
        selected_texts = [item for item in self.scene.selectedItems()
                         if isinstance(item, TextItem)]
        if not selected_texts:
            self.status_bar.showMessage("请先选中要放大的文字")
            return

        for text_item in selected_texts:
            text_item.increase_font_size()

        self.status_bar.showMessage(f"已放大 {len(selected_texts)} 个文字的字体")

    def decrease_text_font_size(self):
        """缩小选中文字的字体"""
        selected_texts = [item for item in self.scene.selectedItems()
                         if isinstance(item, TextItem)]
        if not selected_texts:
            self.status_bar.showMessage("请先选中要缩小的文字")
            return

        for text_item in selected_texts:
            text_item.decrease_font_size()

        self.status_bar.showMessage(f"已缩小 {len(selected_texts)} 个文字的字体")

    def keyPressEvent(self, event):
        """键盘事件处理"""
        if event.key() == Qt.Key_Delete:
            self.delete_selected()
        elif event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
            # Ctrl+Shift 组合键
            if event.key() == Qt.Key_Greater or event.key() == Qt.Key_Period:
                # Ctrl+Shift+> 放大选中文字
                self.increase_text_font_size()
            elif event.key() == Qt.Key_Less or event.key() == Qt.Key_Comma:
                # Ctrl+Shift+< 缩小选中文字
                self.decrease_text_font_size()
            else:
                super().keyPressEvent(event)
        elif event.modifiers() == Qt.ControlModifier:
            if event.key() in (Qt.Key_Equal, Qt.Key_Plus):
                self.zoom_in_selected()
            elif event.key() == Qt.Key_Minus:
                self.zoom_out_selected()
            elif event.key() == Qt.Key_0:
                self.reset_selected_size()
            elif event.key() == Qt.Key_1:
                # Ctrl+1: 导入最近1张图片
                self.import_recent_images(1)
            elif event.key() == Qt.Key_2:
                # Ctrl+2: 导入最近2张图片
                self.import_recent_images(2)
            elif event.key() == Qt.Key_3:
                # Ctrl+3: 导入最近3张图片
                self.import_recent_images(3)
            elif event.key() == Qt.Key_4:
                # Ctrl+4: 导入最近4张图片
                self.import_recent_images(4)
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        """鼠标滚轮事件 - 支持触摸板双指平移和缩放"""
        if event.modifiers() == Qt.ControlModifier:
            # Ctrl+滚轮：缩放视图（不改变图片像素，只是视觉放大）
            if event.angleDelta().y() > 0:
                self.view.scale(1.15, 1.15)
            else:
                self.view.scale(1/1.15, 1/1.15)
            event.accept()
        else:
            # 触摸板双指滑动 = 平移视图
            delta = event.angleDelta()
            h_scroll = self.view.horizontalScrollBar()
            v_scroll = self.view.verticalScrollBar()

            # 水平和垂直滚动（负值是因为滑动方向和滚动方向相反）
            h_scroll.setValue(h_scroll.value() - delta.x())
            v_scroll.setValue(v_scroll.value() - delta.y())
            event.accept()

    def zoom_view_in(self):
        """放大视图（不改变图片像素）"""
        self.view.scale(1.2, 1.2)
        self.status_bar.showMessage("视图已放大（像素不变）")

    def zoom_view_out(self):
        """缩小视图"""
        self.view.scale(1/1.2, 1/1.2)
        self.status_bar.showMessage("视图已缩小")

    def reset_view_zoom(self):
        """重置视图缩放"""
        self.view.resetTransform()
        self.status_bar.showMessage("视图已重置")


def main():
    # 设置Windows任务栏图标（需要在创建QApplication之前）
    try:
        # 设置AppUserModelID，让Windows任务栏显示自定义图标
        myappid = 'ImageComposer.PyQt5.App.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except:
        pass  # 非Windows系统或设置失败时忽略

    # 启用高DPI缩放
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 使用现代风格

    window = ImageComposer()
    # 启动时直接驻守在系统托盘，不显示窗口
    # 显示托盘提示消息
    window.tray_icon.showMessage(
        "图片合成器",
        f"程序已启动并驻守在系统托盘\n快捷键 {window.hotkey} 可打开窗口\n双击托盘图标也可以打开",
        QSystemTrayIcon.Information,
        3000
    )

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
