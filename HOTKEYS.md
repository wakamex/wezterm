# WezTerm Hotkeys Reference

Auto-generated from source. Run `python3 generate-hotkeys.py > HOTKEYS.md` to update.

## Default Key Bindings

| Action | Description | Linux/Win | macOS | Upstream |
|--------|-------------|-----------|-------|----------|
| `ActivateCommandPalette` | Activate Command Palette | Ctrl+Shift+p | Ctrl+Shift+p | same |
| `ActivateCopyMode` | Activate Copy Mode | Ctrl+Shift+x | Ctrl+Shift+x | same |
| `ActivatePaneDirection` | Activate Pane Down | Ctrl+Shift+DownArrow | Ctrl+Shift+DownArrow | same |
| `ActivateTab` | Activate right-most tab | Ctrl+Shift+9 | Cmd+9 | same |
| `CharSelect` | Enter Emoji / Character selection mode | Ctrl+Shift+u | Ctrl+Shift+u | same |
| `CopyTextTo` | Copy to clipboard and primary selection | Ctrl+Insert | Ctrl+Insert | same |
| `DecreaseFontSize` | Decrease font size | Ctrl+Shift+-, Ctrl+- | Cmd+-, Ctrl+- | same |
| `Hide` | Hide/Minimize Window | Ctrl+Shift+m | Cmd+m | same |
| `HideApplication` | Hide Application | Ctrl+Shift+h | Cmd+h | same |
| `IncreaseFontSize` | Increase font size | Ctrl+Shift+=, Ctrl+= | Cmd+=, Ctrl+= | same |
| `MoveTabRelative` | Move tab one place to the right | Ctrl+Shift+PageDown | Ctrl+Shift+PageDown | same |
| `PasteFrom` | Paste from clipboard | Ctrl+Shift+v, Paste | Cmd+v, Paste | same |
| `QuickSelect` | Enter QuickSelect mode | Ctrl+Shift+Space | Ctrl+Shift+Space | same |
| `QuitApplication` | Quit WezTerm | Ctrl+Shift+q | Cmd+q | same |
| `ResetFontSize` | Reset font size | Ctrl+Shift+0, Ctrl+0 | Cmd+0, Ctrl+0 | same |
| `ShowDebugOverlay` | Show debug overlay | Ctrl+Shift+l | Ctrl+Shift+l | same |
| `SpawnWindow` | New Window | Ctrl+Shift+n | Cmd+n | same |
| `ToggleFullScreen` | Toggle full screen mode | Alt+Return | Opt+Return | same |
| `TogglePaneZoomState` | Toggle Pane Zoom | Ctrl+Shift+z | Ctrl+Shift+z | same |

## Actions Without Default Bindings

These can be bound via `config.keys` in your wezterm config.

| Action | Description | Upstream |
|--------|-------------|----------|
| `ActivateKeyTable` | Activate Key Table | - |
| `ActivateLastTab` | Activate the last active tab | - |
| `ActivatePaneByIndex` | Activate Pane By Index | - |
| `ActivateTabRelative` | Activate the tab to the right | - |
| `ActivateTabRelativeNoWrap` | Activate the tab to the right (no wrapping) | - |
| `ActivateWindow` | Activate the preceeding window | - |
| `ActivateWindowRelative` | Activate the next window | - |
| `ActivateWindowRelativeNoWrap` | Activate the next window | - |
| `AdjustPaneSize` | Adjust Pane Size | - |
| `AttachDomain` | Attach Domain | - |
| `ClearKeyTableStack` | Clear the key table stack | - |
| `ClearScrollback` | Clear the scrollback and viewport | - |
| `ClearSelection` | Clears the selection in the current pane | - |
| `CloseCurrentPane` | Close current Pane | - |
| `CloseCurrentTab` | Close current Tab | - |
| `CompleteSelection` | Complete Selection | - |
| `CompleteSelectionOrOpenLinkAtMouseCursor` | Complete Selection Or Open Link At Mouse Cursor | - |
| `Confirmation` | Prompt the user for confirmation | - |
| `CopyMode` | Copy Mode | - |
| `CopyTo` | Copy To | - |
| `DetachDomain` | Detach Domain | - |
| `DisableDefaultAssignment` | Disable Default Assignment | - |
| `EmitEvent` | Emit Event | - |
| `ExtendSelectionToMouseCursor` | Extend Selection To Mouse Cursor | - |
| `InputSelector` | Prompt the user to choose from a list | - |
| `MoveTab` | Move Tab | - |
| `Multiple` | Multiple | - |
| `Nop` | Does nothing | - |
| `OpenLinkAtMouseCursor` | Open link at mouse cursor | - |
| `OpenUri` | Documentation | - |
| `PaneSelect` | Move a pane into its own window | - |
| `PopKeyTable` | Pop the current key table | - |
| `PromptInputLine` | Prompt the user for a line of text | - |
| `QuickSelectArgs` | Enter QuickSelect mode | - |
| `ReloadConfiguration` | Reload Configuration | - |
| `ResetFontAndWindowSize` | Reset the window and font size | - |
| `ResetTerminal` | Reset the terminal emulation state in the current pane | - |
| `RotatePanes` | Rotate Panes | - |
| `ScrollByCurrentEventWheelDelta` | Scroll By Current Event Wheel Delta | - |
| `ScrollByLine` | Scroll By Line | - |
| `ScrollByPage` | Scroll By Page | - |
| `ScrollToBottom` | Scroll to the bottom | - |
| `ScrollToPrompt` | Scroll To Prompt | - |
| `ScrollToTop` | Scroll to the top | - |
| `Search` | Search pane output | - |
| `SelectTextAtMouseCursor` | Select Text At Mouse Cursor | - |
| `SendKey` | Send Key | - |
| `SendString` | Send String | - |
| `SetPaneZoomState` | Set Pane Zoom State | - |
| `SetWindowLevel` | Always on Bottom | - |
| `Show` | Show/Restore Window | - |
| `ShowLauncher` | Show Launcher | - |
| `ShowLauncherArgs` | Show the launcher | - |
| `ShowTabNavigator` | Navigate tabs | - |
| `SpawnCommandInNewTab` | Spawn Command In New Tab | - |
| `SpawnCommandInNewWindow` | Spawn Command In New Window | - |
| `SpawnTab` | Spawn Tab | - |
| `SplitHorizontal` | Split Horizontal | - |
| `SplitPane` | Split Pane | - |
| `SplitVertical` | Split Vertical | - |
| `StartWindowDrag` | Requests a window drag operation from  the window environment | - |
| `SwitchToWorkspace` | Switch To Workspace | - |
| `SwitchWorkspaceRelative` | Switch Workspace Relative | - |
| `ToggleAlwaysOnBottom` | Toggle always on Bottom | - |
| `ToggleAlwaysOnTop` | Toggle always on Top | - |
