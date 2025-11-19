import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
                             QGraphicsPixmapItem, QFileDialog, QMessageBox, QToolBar,
                             QAction, QStatusBar, QGraphicsItem, QSizePolicy, QPushButton,
                             QWidget, QHBoxLayout, QSystemTrayIcon, QMenu, QDialog,
                             QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QStyle)
from PyQt5.QtCore import Qt, QPointF, QRectF, QSize, QPropertyAnimation, pyqtProperty, QSettings, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap, QImage, QPainter, QKeySequence, QIcon
from PIL import Image
import os

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False


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
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


class ImageComposer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ImageComposer", "Settings")
        self.hotkey = self.settings.value("hotkey", "ctrl+win+z")

        # 创建信号发射器用于线程安全的窗口显示
        self.hotkey_emitter = HotkeySignalEmitter()
        self.hotkey_emitter.show_signal.connect(self.show_window)

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

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setBackgroundBrush(Qt.white)

        self.setCentralWidget(self.view)

        # 创建工具栏
        self.create_toolbar()

        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 | Ctrl+O 导入 | Ctrl+E/S 导出 | Ctrl+=/- 缩放 | Delete 删除")

        # 图片计数
        self.image_count = 0

        # 工具栏可见状态
        self.toolbars_visible = True

        # 默认隐藏工具栏
        self.toggle_toolbars()

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
        self.toggle_btn = QPushButton("◀")
        self.toggle_btn.setFixedSize(20, 20)
        self.toggle_btn.setToolTip("隐藏/展开工具栏")
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
        self.toolbar1.insertWidget(self.toolbar1.actions()[0] if self.toolbar1.actions() else None, self.toggle_btn)

        # 导入图片
        import_action = QAction("📁 导入 (Ctrl+O)", self)
        import_action.setShortcut(QKeySequence("Ctrl+O"))
        import_action.setToolTip("导入图片 (Ctrl+O)")
        import_action.triggered.connect(self.import_images)
        self.toolbar1.addAction(import_action)

        # 导出图片 - 添加Ctrl+E快捷键
        export_action = QAction("💾 导出 (Ctrl+E)", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.setToolTip("导出图片 (Ctrl+E 或 Ctrl+S)")
        export_action.triggered.connect(self.export_image)
        self.toolbar1.addAction(export_action)

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

        # 清空画布
        clear_action = QAction("🗑️ 清空", self)
        clear_action.setToolTip("清空画布上的所有图片")
        clear_action.triggered.connect(self.clear_canvas)
        self.toolbar1.addAction(clear_action)

        # 强制换行，开始第二行工具栏
        self.addToolBarBreak()

        # 第二行工具栏：编辑和视图操作
        self.toolbar2 = QToolBar("编辑操作")
        self.toolbar2.setMovable(False)
        self.toolbar2.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toolbar2.setIconSize(QSize(16, 16))
        self.toolbar2.setFloatable(False)
        self.addToolBar(self.toolbar2)

        # 放大图片
        zoom_in_action = QAction("🔍+ 放大 (Ctrl+=)", self)
        zoom_in_action.setShortcut(QKeySequence("Ctrl+="))
        zoom_in_action.setToolTip("放大选中的图片 (Ctrl+=)")
        zoom_in_action.triggered.connect(self.zoom_in_selected)
        self.toolbar2.addAction(zoom_in_action)

        # 缩小图片
        zoom_out_action = QAction("🔍- 缩小 (Ctrl+-)", self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.setToolTip("缩小选中的图片 (Ctrl+-)")
        zoom_out_action.triggered.connect(self.zoom_out_selected)
        self.toolbar2.addAction(zoom_out_action)

        # 重置大小
        reset_size_action = QAction("↺ 重置 (Ctrl+0)", self)
        reset_size_action.setShortcut(QKeySequence("Ctrl+0"))
        reset_size_action.setToolTip("重置选中图片的大小 (Ctrl+0)")
        reset_size_action.triggered.connect(self.reset_selected_size)
        self.toolbar2.addAction(reset_size_action)

        self.toolbar2.addSeparator()

        # 适应窗口
        fit_action = QAction("🖼️ 适应窗口 (Ctrl+P)", self)
        fit_action.setShortcut(QKeySequence("Ctrl+P"))
        fit_action.setToolTip("调整视图以显示所有图片 (Ctrl+P)")
        fit_action.triggered.connect(self.fit_in_view)
        self.toolbar2.addAction(fit_action)

        # 重置视图
        reset_action = QAction("🔄 重置视图", self)
        reset_action.setToolTip("重置视图缩放和位置")
        reset_action.triggered.connect(self.reset_view)
        self.toolbar2.addAction(reset_action)

    def toggle_toolbars(self):
        """切换工具栏的显示/隐藏状态"""
        self.toolbars_visible = not self.toolbars_visible

        if self.toolbars_visible:
            # 展开工具栏
            self.toolbar1.show()
            self.toolbar2.show()
            self.toggle_btn.setText("◀")
            self.toggle_btn.setToolTip("隐藏工具栏")
        else:
            # 隐藏工具栏中除了切换按钮外的所有内容
            for action in self.toolbar1.actions():
                widget = self.toolbar1.widgetForAction(action)
                if widget != self.toggle_btn:
                    action.setVisible(False)

            for action in self.toolbar2.actions():
                action.setVisible(False)

            self.toolbar2.hide()
            self.toggle_btn.setText("▶")
            self.toggle_btn.setToolTip("展开工具栏")

        # 如果隐藏状态，需要重新显示所有action
        if self.toolbars_visible:
            for action in self.toolbar1.actions():
                action.setVisible(True)
            for action in self.toolbar2.actions():
                action.setVisible(True)

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

    def delete_selected(self):
        """删除选中的图片"""
        selected_items = self.scene.selectedItems()

        if not selected_items:
            self.status_bar.showMessage("没有选中的图片")
            return

        for item in selected_items:
            self.scene.removeItem(item)
            self.image_count -= 1

        self.status_bar.showMessage(f"已删除 {len(selected_items)} 张图片")

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
        reply = QMessageBox.question(
            self,
            "确认",
            "确定要清空所有图片吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
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
        """导出合成后的图片（使用原始分辨率）"""
        items = [item for item in self.scene.items() if isinstance(item, DraggablePixmapItem)]

        if not items:
            QMessageBox.warning(self, "警告", "画布上没有图片可导出！")
            return

        # 让用户选择保存位置
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存图片",
            "",
            "PNG图片 (*.png);;JPEG图片 (*.jpg);;所有文件 (*.*)"
        )

        if not file_path:
            return

        try:
            # 计算所有图片的边界框（使用原始尺寸）
            min_x = float('inf')
            min_y = float('inf')
            max_x = float('-inf')
            max_y = float('-inf')

            # 收集所有图片的信息
            image_info = []
            for item in items:
                pos = item.pos()

                # 获取原始图片
                orig_img = item.original_image.copy()

                # 应用用户的缩放
                if item.user_scale != 1.0:
                    new_width = int(orig_img.width * item.user_scale)
                    new_height = int(orig_img.height * item.user_scale)
                    orig_img = orig_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # 位置就是画布上的位置（因为display_scale=1.0）
                orig_x = pos.x()
                orig_y = pos.y()

                image_info.append({
                    'image': orig_img,
                    'x': orig_x,
                    'y': orig_y,
                    'width': orig_img.width,
                    'height': orig_img.height
                })

                min_x = min(min_x, orig_x)
                min_y = min(min_y, orig_y)
                max_x = max(max_x, orig_x + orig_img.width)
                max_y = max(max_y, orig_y + orig_img.height)

            # 添加边距
            padding = 50
            width = int(max_x - min_x + 2 * padding)
            height = int(max_y - min_y + 2 * padding)

            # 创建结果图片（使用原始分辨率）
            if file_path.lower().endswith('.jpg') or file_path.lower().endswith('.jpeg'):
                result = Image.new('RGB', (width, height), 'white')
            else:
                result = Image.new('RGBA', (width, height), (255, 255, 255, 255))

            # 粘贴所有原始图片
            for info in image_info:
                paste_x = int(info['x'] - min_x + padding)
                paste_y = int(info['y'] - min_y + padding)

                img = info['image']

                # 处理透明图片
                if img.mode == 'RGBA' and result.mode == 'RGBA':
                    result.paste(img, (paste_x, paste_y), img)
                else:
                    if img.mode == 'RGBA':
                        # 如果结果是RGB，需要先将RGBA转换
                        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                        rgb_img.paste(img, mask=img.split()[3])
                        result.paste(rgb_img, (paste_x, paste_y))
                    else:
                        result.paste(img, (paste_x, paste_y))

            # 保存结果
            if file_path.lower().endswith('.jpg') or file_path.lower().endswith('.jpeg'):
                result.save(file_path, 'JPEG', quality=95)
            else:
                result.save(file_path, 'PNG')

            QMessageBox.information(
                self,
                "成功",
                f"图片已成功保存到:\n{file_path}\n\n尺寸: {width} x {height} 像素"
            )
            self.status_bar.showMessage(f"图片已导出: {os.path.basename(file_path)} ({width}x{height})")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出图片失败:\n{str(e)}")

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
