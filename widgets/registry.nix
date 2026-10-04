# unloadOnClose defaults to false; set true for content that should release memory.
# One definition per widget; shared by Quickshell and the GNOME adapter.
[
  { id = "example"; label = "Workstation widgets"; iconName = "view-grid-symbolic";
    component = "widgets/example/Widget.qml"; width = 420; height = 580; panelOrder = 0; }
  { id = "compact"; label = "Компактный виджет"; iconName = "starred-symbolic";
    component = "widgets/compact/Widget.qml"; width = 320; height = 240; panelOrder = 1; }
]
