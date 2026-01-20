pyinstaller --onefile \
--hidden-import="sklearn.utils._typedefs" \
--hidden-import pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt5 \
--hidden-import pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyqt5 \
--hidden-import pyqtgraph.imageview.ImageViewTemplate_pyqt5 qcmd.py
