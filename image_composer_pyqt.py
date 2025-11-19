import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
                             QGraphicsPixmapItem, QFileDialog, QMessageBox, QToolBar,
                             QAction, QStatusBar, QGraphicsItem, QSizePolicy)
from PyQt5.QtCore import Qt, QPointF, QRectF, QSize
from PyQt5.QtGui import QPixmap, QImage, QPainter, QKeySequence
from PIL import Image
import os


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
        self.init_ui()

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

    def create_toolbar(self):
        """创建工具栏（分两行显示）"""
        # 第一行工具栏：文件操作
        toolbar1 = QToolBar("文件操作")
        toolbar1.setMovable(False)
        toolbar1.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar1.setIconSize(QSize(16, 16))
        toolbar1.setFloatable(False)
        self.addToolBar(toolbar1)

        # 导入图片
        import_action = QAction("📁 导入 (Ctrl+O)", self)
        import_action.setShortcut(QKeySequence("Ctrl+O"))
        import_action.setToolTip("导入图片 (Ctrl+O)")
        import_action.triggered.connect(self.import_images)
        toolbar1.addAction(import_action)

        # 导出图片 - 添加Ctrl+E快捷键
        export_action = QAction("💾 导出 (Ctrl+E)", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.setToolTip("导出图片 (Ctrl+E 或 Ctrl+S)")
        export_action.triggered.connect(self.export_image)
        toolbar1.addAction(export_action)

        # 额外绑定Ctrl+S快捷键（保持兼容性）
        export_action2 = QAction(self)
        export_action2.setShortcut(QKeySequence("Ctrl+S"))
        export_action2.triggered.connect(self.export_image)
        self.addAction(export_action2)

        toolbar1.addSeparator()

        # 删除选中
        delete_action = QAction("🗑️ 删除 (Del)", self)
        delete_action.setShortcut(QKeySequence("Delete"))
        delete_action.setToolTip("删除选中的图片 (Delete)")
        delete_action.triggered.connect(self.delete_selected)
        toolbar1.addAction(delete_action)

        # 清空画布
        clear_action = QAction("🗑️ 清空", self)
        clear_action.setToolTip("清空画布上的所有图片")
        clear_action.triggered.connect(self.clear_canvas)
        toolbar1.addAction(clear_action)

        # 强制换行，开始第二行工具栏
        self.addToolBarBreak()

        # 第二行工具栏：编辑和视图操作
        toolbar2 = QToolBar("编辑操作")
        toolbar2.setMovable(False)
        toolbar2.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar2.setIconSize(QSize(16, 16))
        toolbar2.setFloatable(False)
        self.addToolBar(toolbar2)

        # 放大图片
        zoom_in_action = QAction("🔍+ 放大 (Ctrl+=)", self)
        zoom_in_action.setShortcut(QKeySequence("Ctrl+="))
        zoom_in_action.setToolTip("放大选中的图片 (Ctrl+=)")
        zoom_in_action.triggered.connect(self.zoom_in_selected)
        toolbar2.addAction(zoom_in_action)

        # 缩小图片
        zoom_out_action = QAction("🔍- 缩小 (Ctrl+-)", self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.setToolTip("缩小选中的图片 (Ctrl+-)")
        zoom_out_action.triggered.connect(self.zoom_out_selected)
        toolbar2.addAction(zoom_out_action)

        # 重置大小
        reset_size_action = QAction("↺ 重置 (Ctrl+0)", self)
        reset_size_action.setShortcut(QKeySequence("Ctrl+0"))
        reset_size_action.setToolTip("重置选中图片的大小 (Ctrl+0)")
        reset_size_action.triggered.connect(self.reset_selected_size)
        toolbar2.addAction(reset_size_action)

        toolbar2.addSeparator()

        # 适应窗口
        fit_action = QAction("🖼️ 适应窗口 (Ctrl+P)", self)
        fit_action.setShortcut(QKeySequence("Ctrl+P"))
        fit_action.setToolTip("调整视图以显示所有图片 (Ctrl+P)")
        fit_action.triggered.connect(self.fit_in_view)
        toolbar2.addAction(fit_action)

        # 重置视图
        reset_action = QAction("🔄 重置视图", self)
        reset_action.setToolTip("重置视图缩放和位置")
        reset_action.triggered.connect(self.reset_view)
        toolbar2.addAction(reset_action)

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
