Mouse & Keyboard Recorder - v1.0.0

This is the initial release of the Mouse & Keyboard Recorder! This application helps you automate repetitive tasks by recording your mouse and keyboard actions and then playing them back. This project was developed with significant AI assistance from Google's Gemini.

This release is a standalone .exe file – no installer is needed.
Key Features:

    Comprehensive Recording: Capture mouse movements (optional), mouse clicks (left, right, middle), scroll wheel actions, and keyboard input.
    Flexible Playback:
        Replay recorded sequences accurately.
        Adjust playback speed: play faster, slower, or even pause.
        Loop recordings for a specified number of repetitions.
        Optionally add delays between looped playbacks.
        Choose to replay with or without the original recorded delays between actions.
    Auto-Clicker: Built-in auto-clicker functionality with a configurable click interval (in seconds).
    Customizable Keybinds:
        Default keybinds for core actions: Record ('1'), Playback ('2'), Exit ('3'), AutoClick ('4').
        Easily change these keybinds via the "Options > Change Keybinds" menu.
    Recording Management:
        Save your recorded sequences with custom names. Each recording is stored in a .json file.
        Load previously saved recordings from a dropdown list.
        Delete unneeded recordings.
        Editable Click Count: The JSON format for saved mouse clicks allows you to manually edit the repetition count for a series of identical clicks if desired (look for "type": "repeated_mouse_click" and its "count" field in the saved .json files).
    Recording Editing:
        Add new left mouse clicks to the end of your current or loaded recording at a user-specified screen position and quantity.
    User Interface:
        Sleek, professional dark theme for comfortable use.
        Toggle the visibility of the "Edit Clicks" section via the "View" menu to customize your workspace (window height adjusts automatically).
        Clear in-app log with timestamps (hh:ss AM/PM format, prefixed with 🕔).
    Robustness & Debugging:
        A dedicated "robust exit" keybind (uses the configured 'Exit' keybind, default '3') designed to forcefully close the application if other keybinds become unresponsive.
        Automatic bugreport.txt generation in the application's folder, logging actions and errors for troubleshooting. This file is reset each time the app starts.
    Help: Integrated "How to use" guide accessible from the "Help" menu.

How to Use / Installation:

    Download: Get the Mourse&KeyboardRecUpdateWorking.exe file (or your chosen executable name).
    Run: No installation is required. Simply place the .exe in a folder of your choice and run it.
    Data Files: The application will create and use the following files and folders in the same directory as the .exe:
        settings.ini: Stores your general settings, UI visibility preferences, and global keybind configurations.
        recordings/: This folder will be created to store your saved recordings (as individual .json files) and the last_recording.json.
        macros/: for future updates im planning on adding macro's to the mouse recorder and this file might already be created.
        bugreport.txt: Logs application activity and any errors encountered. This file is reset each time the app starts.
    Permissions:
        Important: To reliably capture mouse and keyboard events across all applications, you might need to run the executable as an administrator. This is often necessary for global input monitoring tools though I have not encountered this myself.

Thank you for trying out the Mouse & Keyboard Recorder!

Full Changelog: https://github.com/HetBierMannetje/MouseRecorder/commits/v1.0.0
