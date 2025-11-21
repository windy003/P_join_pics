import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
                             QGraphicsPixmapItem, QFileDialog, QMessageBox, QToolBar,
                             QAction, QStatusBar, QGraphicsItem, QSizePolicy, QPushButton,
                             QWidget, QHBoxLayout, QSystemTrayIcon, QMenu, QDialog,
                             QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QStyle,
                             QGraphicsLineItem, QGraphicsPolygonItem, QGraphicsItemGroup)
from PyQt5.QtCore import Qt, QPointF, QRectF, QSize, QPropertyAnimation, pyqtProperty, QSettings, pyqtSignal, QObject, QLineF, QTimer
from PyQt5.QtGui import QPixmap, QImage, QPainter, QKeySequence, QIcon, QPen, QColor, QPolygonF, QBrush
from PIL import Image
import os
from datetime import datetime

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False


# ===== 撤销/重做系统（仅支持箭头操作）=====

class ArrowUndoStack:
    """箭头操作的撤销栈管理器"""
    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []

    def push_add_arrow(self, scene, arrow):
        """添加箭头到撤销栈"""
        self.undo_stack.append({'action': 'add', 'arrow': arrow, 'scene': scene})
        # 执行新命令后清空重做栈
        self.redo_stack.clear()

    def push_delete_arrows(self, scene, arrows):
        """删除箭头到撤销栈"""
        # 保存箭头的状态
        arrow_states = []
        for arrow in arrows:
            arrow_states.append({
                'arrow': arrow,
                'pos': arrow.pos(),
                'z_value': arrow.zValue()
            })
        self.undo_stack.append({'action': 'delete', 'arrows': arrow_states, 'scene': scene})
        # 执行新命令后清空重做栈
        self.redo_stack.clear()

    def undo(self):
        """撤销最后一个命令"""
        if not self.undo_stack:
            return False

        command = self.undo_stack.pop()

        if command['action'] == 'add':
            # 撤销添加 = 移除箭头
            command['scene'].removeItem(command['arrow'])
            self.redo_stack.append(command)
        elif command['action'] == 'delete':
            # 撤销删除 = 恢复箭头
            for state in command['arrows']:
                arrow = state['arrow']
                command['scene'].addItem(arrow)
                arrow.setPos(state['pos'])
                arrow.setZValue(state['z_value'])
            self.redo_stack.append(command)

        return True

    def redo(self):
        """重做最后一个撤销的命令"""
        if not self.redo_stack:
            return False

        command = self.redo_stack.pop()

        if command['action'] == 'add':
            # 重做添加 = 添加箭头
            command['scene'].addItem(command['arrow'])
            command['arrow'].setPos(command['arrow'].pos())
            self.undo_stack.append(command)
        elif command['action'] == 'delete':
            # 重做删除 = 移除箭头
            for state in command['arrows']:
                command['scene'].removeItem(state['arrow'])
            self.undo_stack.append(command)

        return True

    def can_undo(self):
        """是否可以撤销"""
        return len(self.undo_stack) > 0

    def can_redo(self):
        """是否可以重做"""
        return len(self.redo_stack) > 0

    def clear(self):
        """清空撤销栈"""
        self.undo_stack.clear()
        self.redo_stack.clear()


class HotkeySignalEmitter(QObject):
    """用于从keyboard库线程发送信号到Qt主线程的信号发射器"""
    show_signal = pyqtSignal()


class HotkeySettingsDialog(QDialog):
    """快捷键设置对话框"""
    def __init__(self, current_hotkey, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.setModal(True)

        layout = QVBoxLayout()

        # 说明文字
        info_label = QLabel("设置全局快捷键来唤出窗口")
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


class ArrowItem(QGraphicsItemGroup):
    """可拖拽的箭头"""
    def __init__(self, start_point, end_point):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

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
        angle = line.angle() * 3.14159 / 180.0
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
                if isinstance(item, (DraggablePixmapItem, ArrowItem)):
                    max_z = max(max_z, item.zValue())
            self.setZValue(max_z + 1)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


class DraggablePixmapItem(QGraphicsPixmapItem):
    """可拖拽的图片项"""
    def __init__(self, pixmap, original_image, display_scale=1.0):
        super().__init__(pixmap)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setTransformationMode(Qt.SmoothTransformation)

        # 保存原始图片和显示缩放比例
        self.original_image = original_image
        self.display_scale = display_scale  # 原始图片到显示图片的缩放比例
        self.user_scale = 1.0  # 用户编辑时的缩放比例

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
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.main_window and self.main_window.arrow_mode and self.main_window.arrow_start_point:
            # 更新临时线条
            scene_pos = self.mapToScene(event.pos())
            if self.main_window.temp_arrow_line:
                line = QLineF(self.main_window.arrow_start_point, scene_pos)
                self.main_window.temp_arrow_line.setLine(line)
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
                    self.main_window.arrow_undo_stack.push_add_arrow(self.scene(), arrow)

                self.main_window.arrow_start_point = None
            event.accept()  # 标记事件已处理
        else:
            super().mouseReleaseEvent(event)


class ImageComposer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ImageComposer", "Settings")
        self.hotkey = self.settings.value("hotkey", "ctrl+win+z")

        # 创建信号发射器用于线程安全的窗口显示
        self.hotkey_emitter = HotkeySignalEmitter()
        self.hotkey_emitter.show_signal.connect(self.show_window)

        # 创建箭头操作的撤销栈
        self.arrow_undo_stack = ArrowUndoStack()

        self.init_ui()
        self.create_system_tray()
        self.setup_global_hotkey()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("图片合成器 - Image Composer (PyQt5)")
        self.setGeometry(100, 100, 1400, 900)

        # 创建场景和视图
        self.scene = QGraphicsScene()
        self.scene.setSceneRect(0, 0, 3000, 3000)  # 设置更大的场景

        self.view = CustomGraphicsView(self.scene)
        self.view.main_window = self  # 设置对主窗口的引用
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setBackgroundBrush(Qt.white)

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

        # 创建工具栏
        self.create_toolbar()

        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 | Ctrl+O 导入 | Ctrl+E/S 导出 | Ctrl+=/- 缩放 | Delete 删除 | Ctrl+Del 清空 | Ctrl+A 画箭头 | Ctrl+Z 撤销 | Ctrl+Y 重做")

        # 图片计数
        self.image_count = 0

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
        self.show()
        self.activateWindow()
        self.raise_()

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

        # 导出图片 - 添加Ctrl+E快捷键
        export_action = QAction("💾 导出 (Ctrl+E)", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.setToolTip("导出图片 (Ctrl+E 或 Ctrl+S)")
        export_action.triggered.connect(self.export_image)
        self.toolbar1.addAction(export_action)
        self.addAction(export_action)  # 同时添加到主窗口

        # 额外绑定Ctrl+S快捷键（保持兼容性）
        export_action2 = QAction(self)
        export_action2.setShortcut(QKeySequence("Ctrl+S"))
        export_action2.triggered.connect(self.export_image)
        self.addAction(export_action2)

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

        self.toolbar2.addSeparator()

        # 撤销箭头操作
        undo_action = QAction("↶ 撤销 (Ctrl+Z)", self)
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        undo_action.setToolTip("撤销上一个箭头操作 (Ctrl+Z)")
        undo_action.triggered.connect(self.undo_arrow_action)
        self.toolbar2.addAction(undo_action)
        self.addAction(undo_action)

        # 重做箭头操作 - 支持 Ctrl+Y 和 Ctrl+Shift+Z
        redo_action = QAction("↷ 重做 (Ctrl+Y)", self)
        redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        redo_action.setToolTip("重做箭头操作 (Ctrl+Y 或 Ctrl+Shift+Z)")
        redo_action.triggered.connect(self.redo_arrow_action)
        self.toolbar2.addAction(redo_action)
        self.addAction(redo_action)

        # 额外绑定 Ctrl+Shift+Z 快捷键
        redo_action2 = QAction(self)
        redo_action2.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        redo_action2.triggered.connect(self.redo_arrow_action)
        self.addAction(redo_action2)

        self.toolbar2.addSeparator()

        # 放大图片
        zoom_in_action = QAction("🔍+ 放大 (Ctrl+=)", self)
        zoom_in_action.setShortcut(QKeySequence("Ctrl+="))
        zoom_in_action.setToolTip("放大选中的图片 (Ctrl+=)")
        zoom_in_action.triggered.connect(self.zoom_in_selected)
        self.toolbar2.addAction(zoom_in_action)
        self.addAction(zoom_in_action)  # 同时添加到主窗口

        # 缩小图片
        zoom_out_action = QAction("🔍- 缩小 (Ctrl+-)", self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.setToolTip("缩小选中的图片 (Ctrl+-)")
        zoom_out_action.triggered.connect(self.zoom_out_selected)
        self.toolbar2.addAction(zoom_out_action)
        self.addAction(zoom_out_action)  # 同时添加到主窗口

        # 重置大小
        reset_size_action = QAction("↺ 重置 (Ctrl+0)", self)
        reset_size_action.setShortcut(QKeySequence("Ctrl+0"))
        reset_size_action.setToolTip("重置选中图片的大小 (Ctrl+0)")
        reset_size_action.triggered.connect(self.reset_selected_size)
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
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片文件",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp);;所有文件 (*.*)"
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

                # 创建可拖拽的图片项（display_scale=1.0表示不缩放）
                item = DraggablePixmapItem(pixmap, pil_image, display_scale=1.0)

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

        self.status_bar.showMessage(f"已导入 {len(file_paths)} 张图片，画布共有 {self.image_count} 张图片")

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

    def toggle_arrow_mode(self):
        """切换箭头绘制模式"""
        self.arrow_mode = self.arrow_action.isChecked()

        if self.arrow_mode:
            # 进入箭头模式
            self.view.setDragMode(QGraphicsView.NoDrag)
            self.view.viewport().setCursor(Qt.CrossCursor)
            self.status_bar.showMessage("箭头绘制模式：按住鼠标左键拖动绘制箭头 | 再次按 Ctrl+A 退出 | 1分钟无操作自动退出")
            # 启动1分钟定时器
            self.arrow_mode_timer.start(60000)  # 60000毫秒 = 1分钟
        else:
            # 退出箭头模式
            self.view.setDragMode(QGraphicsView.ScrollHandDrag)
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
            # 取消箭头模式的选中状态
            self.arrow_action.setChecked(False)
            # 调用切换方法退出箭头模式
            self.toggle_arrow_mode()
            self.status_bar.showMessage("箭头绘制模式已自动退出（1分钟无操作）")

    def undo_arrow_action(self):
        """撤销箭头操作"""
        if self.arrow_undo_stack.undo():
            self.status_bar.showMessage("已撤销箭头操作")
        else:
            self.status_bar.showMessage("没有可撤销的箭头操作")

    def redo_arrow_action(self):
        """重做箭头操作"""
        if self.arrow_undo_stack.redo():
            self.status_bar.showMessage("已重做箭头操作")
        else:
            self.status_bar.showMessage("没有可重做的箭头操作")

    def delete_selected(self):
        """删除选中的图片或箭头"""
        selected_items = self.scene.selectedItems()

        if not selected_items:
            self.status_bar.showMessage("没有选中的项目")
            return

        image_count = 0
        arrow_count = 0
        arrows_to_delete = []

        for item in selected_items:
            if isinstance(item, DraggablePixmapItem):
                image_count += 1
                self.image_count -= 1
                self.scene.removeItem(item)
            elif isinstance(item, ArrowItem):
                arrow_count += 1
                arrows_to_delete.append(item)
                self.scene.removeItem(item)

        # 将箭头删除操作添加到撤销栈
        if arrows_to_delete:
            self.arrow_undo_stack.push_delete_arrows(self.scene, arrows_to_delete)

        msg = []
        if image_count > 0:
            msg.append(f"{image_count} 张图片")
        if arrow_count > 0:
            msg.append(f"{arrow_count} 个箭头")

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

        # 检查是否有图片或箭头
        has_content = any(isinstance(item, (DraggablePixmapItem, ArrowItem)) for item in all_items)

        if not has_content:
            # 播放错误提示音
            QApplication.beep()
            self.status_bar.showMessage("画布上没有内容可导出！")
            return

        try:
            # 获取用户OneDrive图片目录
            user_home = os.path.expanduser("~")
            save_dir = os.path.join(user_home, "OneDrive", "图片", "Screenshots")

            # 如果目录不存在，创建它
            os.makedirs(save_dir, exist_ok=True)

            # 生成时间戳文件名
            timestamp = datetime.now().strftime("%Y-%m-%d %H %M %S")
            file_path = os.path.join(save_dir, f"{timestamp}.png")

            # 获取场景中所有项目的边界框
            scene_rect = self.scene.itemsBoundingRect()

            # 添加边距
            padding = 50
            scene_rect.adjust(-padding, -padding, padding, padding)

            # 创建QImage用于渲染
            image = QImage(int(scene_rect.width()), int(scene_rect.height()),
                          QImage.Format_ARGB32)
            image.fill(Qt.white)

            # 创建QPainter并渲染场景
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            self.scene.render(painter, QRectF(), scene_rect)
            painter.end()

            # 保存图片
            image.save(file_path, 'PNG')

            # 播放成功提示音
            QApplication.beep()

            # 更新状态栏，显示完整路径
            width = int(scene_rect.width())
            height = int(scene_rect.height())
            self.status_bar.showMessage(f"已保存到: {file_path} ({width}x{height})")

        except Exception as e:
            # 播放错误提示音
            QApplication.beep()
            self.status_bar.showMessage(f"导出失败: {str(e)}")

    def keyPressEvent(self, event):
        """键盘事件处理"""
        if event.key() == Qt.Key_Delete:
            self.delete_selected()
        elif event.modifiers() == Qt.ControlModifier:
            if event.key() in (Qt.Key_Equal, Qt.Key_Plus):
                self.zoom_in_selected()
            elif event.key() == Qt.Key_Minus:
                self.zoom_out_selected()
            elif event.key() == Qt.Key_0:
                self.reset_selected_size()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        """鼠标滚轮事件 - 缩放选中的图片"""
        # 检查是否有选中的图片
        selected_items = [item for item in self.scene.selectedItems()
                         if isinstance(item, DraggablePixmapItem)]

        if selected_items and event.modifiers() == Qt.ControlModifier:
            # Ctrl+滚轮：缩放选中的图片
            if event.angleDelta().y() > 0:
                self.zoom_in_selected()
            else:
                self.zoom_out_selected()
            event.accept()
        else:
            # 否则使用默认行为（缩放视图）
            super().wheelEvent(event)


def main():
    # 启用高DPI缩放
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 使用现代风格

    window = ImageComposer()
    window.showMaximized()  # 启动时最大化窗口

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
