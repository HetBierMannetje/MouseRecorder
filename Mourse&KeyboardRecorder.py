import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, Text
from pynput import mouse, keyboard
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyboardController, Key
import traceback
import configparser
import os
import json
import sys
from datetime import datetime

# Define file paths
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(SCRIPT_DIR, 'settings.ini')
RECORDINGS_FILE = os.path.join(SCRIPT_DIR, 'recordings.json')
BUGREPORT_FILE = os.path.join(SCRIPT_DIR, 'bugreport.txt')

keybinds = {
    'record': {'1'},
    'playback': {'2'},
    'exit': {'3'},
    'auto_click': {'4'}
}

mouse_controller = MouseController()
keyboard_controller = KeyboardController()

# --- Dark Mode Styling Constants ---
ROOT_BG = '#1E1E1E'
FRAME_BG = '#252526'
ELEMENT_BG = '#2D2D30'
TEXT_INPUT_BG = '#3C3C3E'
FOREGROUND_TEXT = '#CCCCCC'
FOREGROUND_DIM = '#888888'
BORDER_COLOR = '#4A4A4A'
HIGHLIGHT_BG = '#007ACC'
HIGHLIGHT_FG = '#FFFFFF'

ACCENT_RED = '#D13438'
ACCENT_GREEN = '#107C10'
ACCENT_YELLOW = '#F7A600'

ACTIVE_BUTTON_BG = '#3E3E42'

def global_exception_handler(exc_type, exc_value, exc_traceback):
    try:
        with open(BUGREPORT_FILE, 'a', encoding='utf-8') as f:
            now = datetime.now()
            time_str = now.strftime("%I:%M:%S%p")
            clock_emoji = "\U0001F553"
            f.write(f"\n{clock_emoji}{time_str} FATAL UNHANDLED EXCEPTION:\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
            f.write("=" * 70 + "\n")
    except Exception as log_e:
        print(f"CRITICAL: Failed to write fatal exception to bug report: {log_e}")

    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = global_exception_handler


class RecorderApp:
    WINDOW_WIDTH = 455
    KEYBIND_FRAME_REMOVED_HEIGHT = 30
    EDIT_CLICKS_SECTION_HEIGHT = 30

    MAX_CONTENT_HEIGHT = 420 - KEYBIND_FRAME_REMOVED_HEIGHT
    _original_MACROS_SECTION_HEIGHT = 55 # Kept for consistent BASE_WINDOW_HEIGHT calculation if needed, though macros are out
    BASE_WINDOW_HEIGHT = MAX_CONTENT_HEIGHT - _original_MACROS_SECTION_HEIGHT - EDIT_CLICKS_SECTION_HEIGHT


    def __init__(self, root):
        self.root = root
        self.bug_report_file_path = BUGREPORT_FILE

        try:
            with open(self.bug_report_file_path, 'w', encoding='utf-8') as f:
                f.write(f"Bug report log session started at {datetime.now().strftime('%Y-%m-%d %I:%M:%S%p')}\n")
                f.write("=" * 70 + "\n")
        except Exception as e:
            print(f"CRITICAL: Could not initialize bug report file '{self.bug_report_file_path}': {e}")

        self.log_to_bug_report("INFO - Application initializing...")


        self.replay_with_original = tk.IntVar(value=1)
        self.loop_var = tk.IntVar(value=0)
        self.loop_count_var = tk.StringVar(value="1")
        self.auto_click_interval_var = tk.StringVar(value="1.0")
        self.playback_speed_var = tk.DoubleVar(value=1.0)
        self.move_var = tk.IntVar(value=0)
        self.inter_playback_delay_var = tk.IntVar(value=0)
        self.inter_playback_delay_seconds_var = tk.StringVar(value="1.0")

        self.listening_for_keybind = None
        self.recording = False
        self.playing_back = False
        self.auto_clicking = False
        self.recorded_events = []
        self.listener_mouse = None
        self.listener_keyboard = None
        self.playback_thread = None
        self.auto_click_thread = None
        self.current_keys = set()
        self.last_log_message = None
        self.last_action_source = "System"

        self.is_editing_add_click_mode = False
        self.waiting_for_edit_click_position = False
        self.edit_captured_click_x = None
        self.edit_captured_click_y = None
        self.edit_add_click_count_var = tk.StringVar(value="1")

        self.robust_exit_current_pressed_keys = set()
        self.robust_exit_thread = None

        self.show_edit_clicks_var = tk.BooleanVar(value=True)

        self._load_settings()
        self._start_robust_exit_listener()


        root.title("Mouse & Keyboard Recorder")
        root.resizable(False, False)

        menubar = tk.Menu(root)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label="Show Edit Clicks Section",
                                    variable=self.show_edit_clicks_var,
                                    command=self._handle_view_toggle)
        menubar.add_cascade(label="View", menu=view_menu)

        options_menu = tk.Menu(menubar, tearoff=0)
        keybind_menu = tk.Menu(options_menu, tearoff=0)
        keybind_actions = ['record', 'playback', 'exit', 'auto_click']
        for action in keybind_actions:
            keybind_menu.add_command(label=action.capitalize(),
                                     command=lambda act=action: self.handle_action("start_listen_keybind",
                                                                                    f"Menu 'Options > Change Keybinds > {act.capitalize()}'",
                                                                                    act))
        options_menu.add_cascade(label="Change Keybinds", menu=keybind_menu)
        menubar.add_cascade(label="Options", menu=options_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="How to use", command=self.show_help)
        menubar.add_cascade(label="Help", menu=help_menu)

        root.config(menu=menubar)

        style = ttk.Style()
        style.theme_use('clam')
        root.config(bg=ROOT_BG)
        style.configure('TFrame', background=FRAME_BG)
        style.configure('TLabel', background=FRAME_BG, foreground=FOREGROUND_TEXT, font=('Segoe UI', 9), padding=(0,1))
        style.configure('Dim.TLabel', background=FRAME_BG, foreground=FOREGROUND_DIM, font=('Segoe UI', 9), padding=(0,1))
        style.configure('TEntry',
                        fieldbackground=TEXT_INPUT_BG,
                        foreground=FOREGROUND_TEXT,
                        insertbackground=FOREGROUND_TEXT,
                        bordercolor=BORDER_COLOR,
                        lightcolor=ELEMENT_BG,
                        darkcolor=ELEMENT_BG,
                        font=('Segoe UI', 9), padding=(2,2))
        style.map('TEntry',
                  bordercolor=[('focus', HIGHLIGHT_BG)],
                  fieldbackground=[('focus', TEXT_INPUT_BG)])
        style.configure('TButton',
                        font=('Segoe UI', 9),
                        padding=(3, 1),
                        background=ELEMENT_BG,
                        foreground=FOREGROUND_TEXT,
                        bordercolor=BORDER_COLOR,
                        relief='raised',
                        borderwidth=1)
        style.map('TButton',
                  background=[('active', ACTIVE_BUTTON_BG), ('pressed', ACTIVE_BUTTON_BG)],
                  foreground=[('active', HIGHLIGHT_FG)],
                  relief=[('pressed', 'sunken'), ('active', 'raised')])
        style.configure('Red.TButton', background=ACCENT_RED, foreground=HIGHLIGHT_FG, font=('Segoe UI', 9, 'bold'))
        style.map('Red.TButton', background=[('active', '#E57373'), ('pressed', '#D32F2F')])
        style.configure('Green.TButton', background=ACCENT_GREEN, foreground=HIGHLIGHT_FG, font=('Segoe UI', 9, 'bold'))
        style.map('Green.TButton', background=[('active', '#81C784'), ('pressed', '#388E3C')])
        style.configure('Yellow.TButton', background=ACCENT_YELLOW, foreground='#000000', font=('Segoe UI', 9, 'bold'))
        style.map('Yellow.TButton', background=[('active', '#FFCA28'), ('pressed', '#FFA000')])
        style.configure('TCheckbutton',
                        background=FRAME_BG,
                        foreground=FOREGROUND_TEXT,
                        indicatorbackground=ELEMENT_BG,
                        indicatorrelief='flat',
                        indicatorborderwidth=1,
                        indicatorbordercolor=BORDER_COLOR,
                        font=('Segoe UI', 9), padding=(2,1))
        style.map('TCheckbutton',
                  background=[('active', FRAME_BG)],
                  indicatorbackground=[('selected', HIGHLIGHT_BG), ('active', ACTIVE_BUTTON_BG)],
                  indicatorforeground=[('selected', HIGHLIGHT_FG)])
        style.configure('Horizontal.TScale',
                        background=ELEMENT_BG,
                        troughcolor=TEXT_INPUT_BG,
                        sliderrelief='flat',
                        sliderlength=18,
                        bordercolor=BORDER_COLOR)
        style.map('Horizontal.TScale',
                  background=[('active', ELEMENT_BG)],
                  troughcolor=[('active', TEXT_INPUT_BG)],
                  sliderbackground=[('active', HIGHLIGHT_BG)])
        style.configure('TCombobox',
                        fieldbackground=TEXT_INPUT_BG,
                        foreground=FOREGROUND_TEXT,
                        selectbackground=HIGHLIGHT_BG,
                        selectforeground=HIGHLIGHT_FG,
                        bordercolor=BORDER_COLOR,
                        arrowcolor=FOREGROUND_TEXT,
                        background=ELEMENT_BG,
                        font=('Segoe UI', 9), padding=(2,2))
        style.map('TCombobox',
                  fieldbackground=[('readonly', TEXT_INPUT_BG), ('focus', TEXT_INPUT_BG)],
                  selectbackground=[('readonly', HIGHLIGHT_BG),('focus', HIGHLIGHT_BG)],
                  foreground=[('focus', FOREGROUND_TEXT)],
                  arrowcolor=[('hover', HIGHLIGHT_BG)])
        self.root.option_add('*TCombobox*Listbox.background', TEXT_INPUT_BG)
        self.root.option_add('*TCombobox*Listbox.foreground', FOREGROUND_TEXT)
        self.root.option_add('*TCombobox*Listbox.selectBackground', HIGHLIGHT_BG)
        self.root.option_add('*TCombobox*Listbox.selectForeground', HIGHLIGHT_FG)

        self.log_frame_instance = ttk.Frame(root)
        self.text_display = tk.Text(self.log_frame_instance, height=10, width=58, font=('Consolas', 9),
                                    wrap=tk.WORD,
                                    state=tk.DISABLED, bg=TEXT_INPUT_BG, fg=FOREGROUND_TEXT, insertbackground=FOREGROUND_TEXT,
                                    highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=BORDER_COLOR, borderwidth=0, relief='flat')
        self.text_display.pack(fill=tk.X)

        self.status_label = ttk.Label(root, text="", foreground=ACCENT_RED, font=("Segoe UI", 9, 'bold'))
        self.move_mouse = bool(self.move_var.get())
        self.saved_recordings = {}
        self.recording_name_var = tk.StringVar(value="")
        self.selected_recording_var = tk.StringVar()
        self._load_recordings()

        self.top_frame = ttk.Frame(root)
        left_btn_frame = ttk.Frame(self.top_frame)
        self.record_btn = ttk.Button(left_btn_frame, text="● REC", command=lambda: self.handle_action("toggle_recording", "UI Button 'Record'"), style='Red.TButton', width=10)
        self.play_btn = ttk.Button(left_btn_frame, text="▶ PLAY", command=lambda: self.handle_action("toggle_playback", "UI Button 'Playback'"), style='Green.TButton', width=10)
        self.auto_click_btn = ttk.Button(left_btn_frame, text="AutoClick", command=lambda: self.handle_action("toggle_auto_click", "UI Button 'AutoClick'"), style='Yellow.TButton', width=10)
        self.auto_click_interval_label = ttk.Label(left_btn_frame, text="Interval (s):", style='Dim.TLabel')
        self.auto_click_interval_entry = ttk.Entry(left_btn_frame, textvariable=self.auto_click_interval_var, width=6, justify='center')
        self.exit_btn = ttk.Button(self.top_frame, text="Exit", command=lambda: self.handle_action("exit_app", "UI Button 'Exit'"), width=8)

        self.bottom_frame = ttk.Frame(root)
        self.replay_with_original_check = ttk.Checkbutton(self.bottom_frame, text="Replay w/ delay", variable=self.replay_with_original, command=self._save_settings_on_interaction)
        self.loop_check = ttk.Checkbutton(self.bottom_frame, text="Loop", variable=self.loop_var, command=self._save_settings_on_interaction)
        self.loop_count_entry = ttk.Entry(self.bottom_frame, textvariable=self.loop_count_var, width=3, justify='center')
        self.loop_count_entry.bind("<FocusOut>", self._validate_and_save_loop_count)
        self.loop_count_entry.bind("<Return>", self._validate_and_save_loop_count)
        self.move_check = ttk.Checkbutton(self.bottom_frame, text="Replay Movement", variable=self.move_var, command=self.set_move_mode)

        self.playback_speed_frame = ttk.Frame(root)
        playback_speed_text_label = ttk.Label(self.playback_speed_frame, text="Playback Speed:", style='Dim.TLabel')
        self.playback_speed_var.trace_add("write", self.update_playback_speed_label)
        self.playback_speed_slider = ttk.Scale(self.playback_speed_frame, from_=-2.0, to=5.0, orient=tk.HORIZONTAL, variable=self.playback_speed_var, command=self.update_playback_speed_label)
        self.playback_speed_slider.bind("<ButtonRelease-1>", self._save_settings_on_interaction)

        self.playback_speed_label = ttk.Label(self.playback_speed_frame, text="1.0x", width=10, anchor='e')

        self.recording_presets_frame = ttk.Frame(root)
        recording_name_text_label = ttk.Label(self.recording_presets_frame, text="Recording Name:", style='Dim.TLabel')
        self.recording_name_entry = ttk.Entry(self.recording_presets_frame, textvariable=self.recording_name_var, width=20)
        self.save_recording_btn = ttk.Button(self.recording_presets_frame, text="Save", command=lambda: self.handle_action("save_current_recording", "UI Button 'Save Recording'"), width=8)

        self.load_delete_frame = ttk.Frame(root)
        load_delete_text_label = ttk.Label(self.load_delete_frame, text="Load/Delete:", style='Dim.TLabel')
        self.recording_combobox = ttk.Combobox(self.load_delete_frame, textvariable=self.selected_recording_var, state="readonly", width=18)
        self.load_recording_btn = ttk.Button(self.load_delete_frame, text="Load", command=lambda: self.handle_action("load_selected_recording", "UI Button 'Load Recording'"), width=8)
        self.delete_recording_btn = ttk.Button(self.load_delete_frame, text="Delete", command=lambda: self.handle_action("delete_selected_recording", "UI Button 'Delete Recording'"), width=8)

        self.inter_playback_delay_frame = ttk.Frame(root)
        self.inter_playback_delay_check = ttk.Checkbutton(self.inter_playback_delay_frame, text="Delay Between Loops", variable=self.inter_playback_delay_var, command=self._save_settings_on_interaction)
        inter_playback_delay_text_label = ttk.Label(self.inter_playback_delay_frame, text="Delay (s):", style='Dim.TLabel')
        self.inter_playback_delay_entry = ttk.Entry(self.inter_playback_delay_frame, textvariable=self.inter_playback_delay_seconds_var, width=6, justify='center')

        self.edit_add_click_control_frame = ttk.Frame(root)

        self.top_frame.pack(fill=tk.X, pady=(3,1), padx=5)
        left_btn_frame.pack(side=tk.LEFT)
        self.record_btn.pack(side=tk.LEFT, padx=2)
        self.play_btn.pack(side=tk.LEFT, padx=2)
        self.auto_click_btn.pack(side=tk.LEFT, padx=2)
        self.auto_click_interval_label.pack(side=tk.LEFT, padx=(5,1))
        self.auto_click_interval_entry.pack(side=tk.LEFT, padx=(1,2))
        self.auto_click_interval_entry.bind("<FocusOut>", self.validate_auto_click_interval_and_save)
        self.auto_click_interval_entry.bind("<Return>", self.validate_auto_click_interval_and_save)
        self.exit_btn.pack(side=tk.RIGHT, padx=5)

        self.bottom_frame.pack(fill=tk.X, pady=1, padx=5)
        self.replay_with_original_check.pack(side=tk.LEFT, padx=(0,5))
        self.loop_check.pack(side=tk.LEFT, padx=(5, 0))
        self.loop_count_entry.pack(side=tk.LEFT, padx=(2, 10))
        self.move_check.pack(side=tk.LEFT, padx=(10,5))

        self.playback_speed_frame.pack(fill=tk.X, pady=1, padx=5)
        playback_speed_text_label.pack(side=tk.LEFT)
        self.playback_speed_slider.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5,0))
        self.playback_speed_label.pack(side=tk.RIGHT, padx=(5,0))

        self.log_frame_instance.pack(fill=tk.X, pady=(3,1), padx=5)

        self.recording_presets_frame.pack(fill=tk.X, pady=1, padx=5)
        recording_name_text_label.pack(side=tk.LEFT)
        self.recording_name_entry.pack(side=tk.LEFT, padx=(5, 0))
        self.save_recording_btn.pack(side=tk.LEFT, padx=5)

        self.load_delete_frame.pack(fill=tk.X, pady=(0,1), padx=5)
        load_delete_text_label.pack(side=tk.LEFT)
        self.recording_combobox.pack(side=tk.LEFT, padx=5)
        self.recording_combobox.bind("<<ComboboxSelected>>", self.on_recording_selected)
        self.load_recording_btn.pack(side=tk.LEFT, padx=5)
        self.delete_recording_btn.pack(side=tk.LEFT, padx=5)

        self.inter_playback_delay_frame.pack(fill=tk.X, pady=1, padx=5)
        self.inter_playback_delay_check.pack(side=tk.LEFT)
        inter_playback_delay_text_label.pack(side=tk.LEFT, padx=(10, 0))
        self.inter_playback_delay_entry.pack(side=tk.LEFT, padx=(2,0))
        self.inter_playback_delay_entry.bind("<FocusOut>", self.validate_inter_playback_delay_and_save)
        self.inter_playback_delay_entry.bind("<Return>", self.validate_inter_playback_delay_and_save)

        self._setup_initial_add_click_ui()
        self._toggle_ui_sections_visibility()
        self._update_recording_combobox()
        self.log_to_bug_report("INFO - Application UI constructed.")
        self.update_playback_speed_label()

    def _save_settings_on_interaction(self, event=None):
        self.log_to_bug_report(f"OPTION_CHANGE - UI option changed, saving settings.")
        self._save_settings()

    def _handle_view_toggle(self):
        self._toggle_ui_sections_visibility(triggered_by_menu=True)
        self._save_settings()

    def _toggle_ui_sections_visibility(self, *args, triggered_by_menu=False):
        if hasattr(self, 'edit_add_click_control_frame') and self.edit_add_click_control_frame.winfo_ismapped():
            self.edit_add_click_control_frame.pack_forget()
        if hasattr(self, 'status_label') and self.status_label.winfo_ismapped():
            self.status_label.pack_forget()

        current_height = self.BASE_WINDOW_HEIGHT
        log_actions = []

        if self.show_edit_clicks_var.get():
            self.edit_add_click_control_frame.pack(fill=tk.X, pady=(1,1), padx=5)
            current_height += self.EDIT_CLICKS_SECTION_HEIGHT
            log_actions.append("Edit Clicks shown")
        else:
            log_actions.append("Edit Clicks hidden")

        self.status_label.pack(pady=(1,0))
        self.root.geometry(f"{self.WINDOW_WIDTH}x{current_height}")

        if triggered_by_menu:
                 self.log_to_bug_report(f"UI_ACTION - View toggled: {', '.join(log_actions)}. New height: {current_height}px.")
        self.root.update_idletasks()

    def log_to_bug_report(self, message):
        try:
            now = datetime.now()
            time_str = now.strftime("%I:%M:%S%p")
            clock_emoji = "\U0001F553"

            with open(self.bug_report_file_path, 'a', encoding='utf-8') as f:
                f.write(f"{clock_emoji}{time_str} {message}\n")
        except Exception as e:
            print(f"CRITICAL: Failed to write to bug report file: {e}")
            print(f"Original bug report message: {message}")

    def handle_action(self, action_name, source_description, *args):
        self.last_action_source = source_description
        self.log_to_bug_report(f"TRIGGER - Action '{action_name}' initiated by: {source_description}.")
        method_to_call = getattr(self, action_name, None)
        if callable(method_to_call):
            try:
                method_to_call(*args)
            except Exception as e:
                err_msg = f"Error during action '{action_name}' (triggered by {source_description}): {e}"
                self.log_message(err_msg)
                self.log_to_bug_report(f"ERROR - {err_msg}\n{traceback.format_exc()}")
        else:
            err_msg = f"Attempted to call invalid action: {action_name}"
            self.log_message(err_msg)
            self.log_to_bug_report(f"ERROR - {err_msg}")


    def _force_exit_app_immediately(self):
        print("ROBUST EXIT TRIGGERED: Forcing application termination.")
        try:
            if hasattr(self, 'bug_report_file_path'):
                with open(self.bug_report_file_path, 'a', encoding='utf-8') as f:
                    now = datetime.now()
                    time_str = now.strftime("%I:%M:%S%p")
                    clock_emoji = "\U0001F553"
                    f.write(f"{clock_emoji}{time_str} EMERGENCY - Robust exit triggered. Forcing termination.\n")
        except:
            pass
        os._exit(0)

    def _robust_on_press(self, key):
        try:
            key_str = self._get_key_display_name(key)
            self.robust_exit_current_pressed_keys.add(key_str)
        except Exception:
            pass

    def _robust_on_release(self, key):
        try:
            key_str = self._get_key_display_name(key)
            exit_combo_keys = keybinds.get('exit', {'3'})

            active_robust_combo_check_keys = self.robust_exit_current_pressed_keys.copy()
            if key_str in exit_combo_keys and exit_combo_keys.issubset(active_robust_combo_check_keys):
                if len(active_robust_combo_check_keys) == len(exit_combo_keys):
                    self._force_exit_app_immediately()

            if key_str in self.robust_exit_current_pressed_keys:
                self.robust_exit_current_pressed_keys.remove(key_str)
        except Exception:
            pass

    def _robust_exit_listener_thread_target(self):
        try:
            with keyboard.Listener(on_press=self._robust_on_press, on_release=self._robust_on_release) as self.robust_exit_listener_instance:
                self.robust_exit_listener_instance.join()
        except Exception as e:
            print(f"CRITICAL - Robust exit listener failed to start or crashed: {e}")
            if hasattr(self, 'bug_report_file_path'):
                try:
                    with open(self.bug_report_file_path, 'a', encoding='utf-8') as f:
                        f.write(f"CRITICAL - Robust exit listener thread crashed: {e}\n{traceback.format_exc()}\n")
                except:
                    pass


    def _start_robust_exit_listener(self):
        self.robust_exit_thread = threading.Thread(target=self._robust_exit_listener_thread_target, daemon=True)
        self.robust_exit_thread.start()


    def _setup_initial_add_click_ui(self):
        for widget in self.edit_add_click_control_frame.winfo_children():
            widget.destroy()

        self.initial_edit_add_click_button = ttk.Button(self.edit_add_click_control_frame,
                                                        text="Edit: Add Clicks",
                                                        command=lambda: self.handle_action("initiate_add_click_mode", "UI Button 'Edit: Add Clicks'"),
                                                        width=15)
        self.initial_edit_add_click_button.pack(side=tk.LEFT, padx=2)

        self.edit_click_pos_label = ttk.Label(self.edit_add_click_control_frame, text="")
        self.edit_click_count_entry = ttk.Entry(self.edit_add_click_control_frame,
                                                textvariable=self.edit_add_click_count_var, width=5, justify='center')
        self.edit_click_confirm_button = ttk.Button(self.edit_add_click_control_frame, text="Confirm Add",
                                                    command=lambda: self.handle_action("confirm_add_clicks_to_recording", "UI Button 'Confirm Add Clicks'"), width=12)
        self.edit_click_cancel_button = ttk.Button(self.edit_add_click_control_frame, text="Cancel Edit",
                                                   command=lambda: self.handle_action("cancel_add_click_mode", "UI Button 'Cancel Edit Clicks'"), width=10)


    def initiate_add_click_mode(self):
        if not self.recorded_events and not self.recording:
            self.log_message("No recording loaded or in progress to add clicks to.")
            self.log_to_bug_report("WARNING - Add Clicks: No recording available.")
            messagebox.showwarning("Edit Recording", "Please record or load a recording before adding clicks.", parent=self.root)
            return

        if self.is_editing_add_click_mode or self.waiting_for_edit_click_position:
            self.log_to_bug_report("INFO - Add Clicks: Already in add click mode or waiting for position.")
            return

        self.is_editing_add_click_mode = True
        self.waiting_for_edit_click_position = True
        self.log_message("ADD CLICKS MODE: Click on the screen to set target position for new clicks.")

        self.initial_edit_add_click_button.pack_forget()

        for widget in self.edit_add_click_control_frame.winfo_children():
            widget.destroy()

        status_label = ttk.Label(self.edit_add_click_control_frame, text="Click screen for position...")
        status_label.pack(side=tk.LEFT, padx=2)

        cancel_btn = ttk.Button(self.edit_add_click_control_frame, text="Cancel Add",
                                 command=lambda: self.handle_action("cancel_add_click_mode", "UI Button 'Cancel Add' in position selection"), width=12)
        cancel_btn.pack(side=tk.LEFT, padx=2)


    def _update_ui_for_add_click_confirmation(self):
        if not self.is_editing_add_click_mode: return

        self.log_to_bug_report(f"STATE - Add Clicks: Position ({self.edit_captured_click_x},{self.edit_captured_click_y}) captured. Awaiting count.")
        for widget in self.edit_add_click_control_frame.winfo_children():
            widget.destroy()

        self.edit_click_pos_label = ttk.Label(self.edit_add_click_control_frame,
                                             text=f"Pos: ({self.edit_captured_click_x},{self.edit_captured_click_y})")
        self.edit_click_pos_label.pack(side=tk.LEFT, padx=2)

        ttk.Label(self.edit_add_click_control_frame, text="Count:").pack(side=tk.LEFT, padx=(5,0))
        self.edit_click_count_entry = ttk.Entry(self.edit_add_click_control_frame,
                                                textvariable=self.edit_add_click_count_var, width=5, justify='center')
        self.edit_click_count_entry.pack(side=tk.LEFT, padx=2)
        self.edit_click_count_entry.focus_set()

        self.edit_click_confirm_button = ttk.Button(self.edit_add_click_control_frame, text="Add These Clicks",
                                                    command=lambda: self.handle_action("confirm_add_clicks_to_recording","UI Button 'Add These Clicks'"), width=15)
        self.edit_click_confirm_button.pack(side=tk.LEFT, padx=2)

        self.edit_click_cancel_button = ttk.Button(self.edit_add_click_control_frame, text="Cancel",
                                                   command=lambda: self.handle_action("cancel_add_click_mode", "UI Button 'Cancel' in count confirmation"), width=8)
        self.edit_click_cancel_button.pack(side=tk.LEFT, padx=2)


    def confirm_add_clicks_to_recording(self):
        if self.edit_captured_click_x is None or self.edit_captured_click_y is None:
            self.log_to_bug_report("ERROR - Add Clicks: No position captured before confirm.")
            self.cancel_add_click_mode()
            return

        try:
            num_clicks = int(self.edit_add_click_count_var.get())
            if num_clicks <= 0:
                self.log_message("Number of clicks must be positive.")
                self.log_to_bug_report(f"WARNING - Add Clicks: Invalid count entered ({self.edit_add_click_count_var.get()}).")
                messagebox.showerror("Add Clicks", "Number of clicks must be a positive integer.", parent=self.root)
                return
        except ValueError:
            self.log_message("Invalid number of clicks.")
            self.log_to_bug_report(f"ERROR - Add Clicks: Non-integer count entered ({self.edit_add_click_count_var.get()}).")
            messagebox.showerror("Add Clicks", "Invalid number for clicks. Please enter an integer.", parent=self.root)
            return

        button_to_add = Button.left.name
        current_timestamp_base = time.time()
        if self.recorded_events:
            current_timestamp_base = self.recorded_events[-1][-1] + 0.1


        for i in range(num_clicks):
            press_event_time = current_timestamp_base + (i * 0.05)
            release_event_time = press_event_time + 0.02

            press_event = ('mouse_click', self.edit_captured_click_x, self.edit_captured_click_y,
                           button_to_add, True, press_event_time)
            self.recorded_events.append(press_event)
            release_event = ('mouse_click', self.edit_captured_click_x, self.edit_captured_click_y,
                             button_to_add, False, release_event_time)
            self.recorded_events.append(release_event)

        log_msg_ui = f"{num_clicks} click(s) added at ({self.edit_captured_click_x},{self.edit_captured_click_y}) to the recording."
        self.log_message(log_msg_ui)
        self.log_to_bug_report(f"ACTION_DETAIL - Add Clicks: {log_msg_ui}")
        self.log_to_bug_report(f"INFO - Recording now has {len(self.recorded_events)} events.")

        self.cancel_add_click_mode()


    def cancel_add_click_mode(self):
        if self.is_editing_add_click_mode:
                 self.log_to_bug_report("ACTION - Add Clicks: Mode cancelled.")

        self.is_editing_add_click_mode = False
        self.waiting_for_edit_click_position = False
        self.edit_captured_click_x = None
        self.edit_captured_click_y = None
        self.edit_add_click_count_var.set("1")
        self._setup_initial_add_click_ui()

    def _get_key_display_name(self, key):
        try:
            if hasattr(key, 'char') and key.char is not None:
                return key.char.lower()
            if hasattr(key, 'name'):
                return key.name.lower()
            if isinstance(key, keyboard.KeyCode):
                if key.vk is not None:
                    if 48 <= key.vk <= 57:
                        return chr(key.vk)
                    if 65 <= key.vk <= 90:
                        return chr(key.vk).lower()
                s = str(key).lower()
                if len(s) > 2 and s.startswith("'") and s.endswith("'"): s = s[1:-1]
                return s
            s = str(key).lower().replace('key.', '')
            if len(s) > 2 and s.startswith("'") and s.endswith("'"): s = s[1:-1]
            return s
        except Exception as e:
            self.log_to_bug_report(f"CRITICAL_UTIL - _get_key_display_name failed for key '{str(key)}': {e}\n{traceback.format_exc()}")
            return f"<UnkKey:{str(key)}>"


    def _load_settings(self):
        self.log_to_bug_report("INFO - Attempting to load settings from INI...")
        try:
            config = configparser.ConfigParser()
            config.read(SETTINGS_FILE)

            if 'Keybinds' in config:
                for action in keybinds.keys():
                    saved_combo_str = config.get('Keybinds', action, fallback=None)
                    if saved_combo_str is not None:
                        keybinds[action] = set(saved_combo_str.split(',')) if saved_combo_str else set()

            if 'General' in config:
                self.replay_with_original.set(config.getboolean('General', 'replay_with_original', fallback=self.replay_with_original.get()))
                self.loop_var.set(config.getboolean('General', 'loop', fallback=self.loop_var.get()))
                self.loop_count_var.set(config.get('General', 'loop_count', fallback=self.loop_count_var.get()))
                self.move_var.set(config.getboolean('General', 'record_movement', fallback=self.move_var.get()))
                self.auto_click_interval_var.set(config.get('General', 'auto_click_interval', fallback=self.auto_click_interval_var.get()))
                self.playback_speed_var.set(config.getfloat('General', 'playback_speed', fallback=self.playback_speed_var.get()))
                self.inter_playback_delay_var.set(config.getboolean('General', 'inter_playback_delay', fallback=self.inter_playback_delay_var.get()))
                self.inter_playback_delay_seconds_var.set(config.get('General', 'inter_playback_delay_seconds', fallback=self.inter_playback_delay_seconds_var.get()))
                self.show_edit_clicks_var.set(config.getboolean('General', 'show_edit_clicks', fallback=True))

            self.log_to_bug_report("INFO - Settings (including UI visibility) loaded successfully from INI.")
        except Exception as e:
            self.log_to_bug_report(f"ERROR - Failed to load settings from INI: {e}\n{traceback.format_exc()}")


    def _save_settings(self):
        self.log_to_bug_report("INFO - Attempting to save settings to INI...")
        try:
            config = configparser.ConfigParser()
            config['Keybinds'] = {}
            for action, combo_set in keybinds.items():
                config['Keybinds'][action] = ",".join(sorted(list(combo_set)))

            config['General'] = {}
            config['General']['replay_with_original'] = str(self.replay_with_original.get())
            config['General']['loop'] = str(self.loop_var.get())
            config['General']['loop_count'] = self.loop_count_var.get()
            config['General']['record_movement'] = str(self.move_var.get())
            config['General']['auto_click_interval'] = self.auto_click_interval_var.get()
            config['General']['playback_speed'] = str(self.playback_speed_var.get())
            config['General']['inter_playback_delay'] = str(self.inter_playback_delay_var.get())
            config['General']['inter_playback_delay_seconds'] = self.inter_playback_delay_seconds_var.get()
            config['General']['show_edit_clicks'] = str(self.show_edit_clicks_var.get())

            with open(SETTINGS_FILE, 'w') as configfile:
                config.write(configfile)
            self.log_to_bug_report("INFO - Settings (including UI visibility) saved successfully to INI.")
        except Exception as e:
            self.log_message(f"Error saving settings: {e}")
            self.log_to_bug_report(f"ERROR - Failed to save settings to INI: {e}\n{traceback.format_exc()}")

    def _load_recordings(self):
        if os.path.exists(RECORDINGS_FILE):
            try:
                with open(RECORDINGS_FILE, 'r') as f:
                    def object_hook(dct):
                        if '__tuple__' in dct: return tuple(dct['__tuple__'])
                        elif '__button__' in dct:
                            try: return getattr(Button, dct['__button__'])
                            except AttributeError: return dct['__button__']
                        elif '__key__' in dct:
                            try: return getattr(Key, dct['__key__'])
                            except AttributeError: return dct['__key__']
                        return dct
                    self.saved_recordings = json.load(f, object_hook=object_hook)
            except json.JSONDecodeError as e:
                self.log_message(f"Error decoding recordings file: {e}. Creating new.")
                self.log_to_bug_report(f"ERROR - Decoding recordings file: {e}. Creating new.\n{traceback.format_exc()}")
                self.saved_recordings = {}
            except Exception as e:
                self.log_message(f"Error loading recordings: {e}")
                self.log_to_bug_report(f"ERROR - Loading recordings: {e}.\n{traceback.format_exc()}")
                self.saved_recordings = {}
        else:
            self.saved_recordings = {}

    def _save_recordings(self):
        try:
            class CustomEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, tuple): return {'__tuple__': list(obj)}
                    elif isinstance(obj, Button): return {'__button__': obj.name}
                    elif isinstance(obj, Key): return {'__key__': obj.name}
                    return json.JSONEncoder.default(self, obj)
            with open(RECORDINGS_FILE, 'w') as f:
                json.dump(self.saved_recordings, f, indent=4, cls=CustomEncoder)
            self.log_to_bug_report(f"INFO - Saved {len(self.saved_recordings)} recordings successfully.")
        except Exception as e:
            self.log_message(f"Error saving recordings: {e}")
            self.log_to_bug_report(f"ERROR - Saving recordings: {e}.\n{traceback.format_exc()}")


    def _update_recording_combobox(self):
        try:
            self.recording_combobox['values'] = sorted(list(self.saved_recordings.keys()))
            if self.selected_recording_var.get() not in self.saved_recordings:
                self.selected_recording_var.set("")
        except Exception as e:
            self.log_to_bug_report(f"ERROR - Updating recording combobox: {e}\n{traceback.format_exc()}")


    def save_current_recording(self):
        name = self.recording_name_var.get().strip()
        if not name:
            self.log_message("Please enter a name for the recording.")
            return
        if not self.recorded_events:
            self.log_message("No events recorded to save!")
            return

        self.saved_recordings[name] = list(self.recorded_events)
        self._save_recordings()
        self._update_recording_combobox()
        self.log_message(f"Recording '{name}' saved.")
        self.log_to_bug_report(f"ACTION_DETAIL - Recording '{name}' saved with {len(self.recorded_events)} events. (Source: {self.last_action_source})")
        self.recording_name_var.set("")

    def load_selected_recording(self):
        if self.is_editing_add_click_mode: self.cancel_add_click_mode()
        name = self.selected_recording_var.get()
        if not name:
            self.log_message("Please select a recording to load.")
            return
        if name not in self.saved_recordings:
            self.log_message(f"Recording '{name}' not found.")
            return
        if self.recording or self.playing_back or self.auto_clicking:
            self.log_message("Cannot load while active.")
            return

        self.recorded_events = list(self.saved_recordings[name])
        self.log_message(f"Recording '{name}' loaded. {len(self.recorded_events)} events.")
        self.log_to_bug_report(f"ACTION_DETAIL - Recording '{name}' loaded with {len(self.recorded_events)} events. (Source: {self.last_action_source})")

    def delete_selected_recording(self):
        if self.is_editing_add_click_mode: self.cancel_add_click_mode()
        name = self.selected_recording_var.get()
        if not name:
            self.log_message("Please select a recording to delete.")
            return
        if name not in self.saved_recordings:
            self.log_message(f"Recording '{name}' not found.")
            return

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{name}'?", parent=self.root):
            self.log_to_bug_report(f"INFO - User confirmed deletion of recording '{name}'. (Source: {self.last_action_source})")
            del self.saved_recordings[name]
            self._save_recordings()
            self._update_recording_combobox()
            self.selected_recording_var.set("")
            self.log_message(f"Recording '{name}' deleted.")
            self.log_to_bug_report(f"ACTION_DETAIL - Recording '{name}' deleted.")
        else:
            self.log_to_bug_report(f"INFO - User cancelled deletion of recording '{name}'. (Source: {self.last_action_source})")


    def on_recording_selected(self, event):
        if self.is_editing_add_click_mode: self.cancel_add_click_mode()
        selected_name = self.selected_recording_var.get()
        if selected_name:
            self.log_message(f"Selected recording: '{selected_name}'")
            self.log_to_bug_report(f"INFO - Recording selected from combobox: '{selected_name}'.")

    def show_help(self):
        if self.is_editing_add_click_mode: self.cancel_add_click_mode()
        self.log_to_bug_report("ACTION - Help dialog shown (triggered by menu).")
        help_text = (
            "Welcome to the Mouse & Keyboard Recorder!\n\n"
            "This tool helps you record your mouse and keyboard actions "
            "and then play them back automatically. You can also use an auto-clicker.\n\n"
            "----------------------------------------\n"
            "  Main Actions (Buttons & Keybinds)\n"
            "----------------------------------------\n"
            "● REC (Record / Default: '1'):\n"
            "  - Click to start recording your mouse (if enabled via 'Replay Movement'), clicks, and keystrokes.\n"
            "  - The button changes to '■ STOP'. Click again or use the keybind to finish.\n\n"

            "▶ PLAY (Playback / Default: '2'):\n"
            "  - Click to play back the last recorded or loaded sequence.\n"
            "  - The button changes to '■ STOP'. Click again or use the keybind to halt playback.\n\n"

            "AutoClick (Default: '4'):\n"
            "  - Click to start/stop rapid left mouse clicks at your current mouse pointer position.\n"
            "  - Interval (s): Set the time (in seconds) between each click in the adjacent field. Set to 0 for fastest possible.\n\n" # Modified help

            "Exit (Default: '3'):\n"
            "  - Closes the application. Settings and recordings are saved.\n\n"

            "----------------------------------------\n"
            "  Playback Settings\n"
            "----------------------------------------\n"
            "☑ Replay w/ delay:\n"
            "  - Checked: Playback uses the original pauses and timings from your recording.\n"
            "  - Unchecked: Actions play back as quickly as possible.\n\n"

            "☑ Loop & Count [  ]:\n"
            "  - Check 'Loop' and enter a number (e.g., 5) in the small box to make the playback repeat that many times.\n\n"

            "☑ Delay Between Loops & Delay (s) [  ]:\n"
            "  - If 'Loop' is active, check this and set a pause (in seconds) that will occur after each full playback cycle before the next one begins.\n\n"

            "Playback Speed (Slider):\n"
            "  - Drag the slider to change the speed of playback.\n"
            "    - Right (>1x): Faster. | Left (<1x): Slower. | 0x: Paused.\n\n"

            "----------------------------------------\n"
            "  Recording Settings\n"
            "----------------------------------------\n"
            "☑ Replay Movement:\n"
            "  - Checked: Mouse movements are recorded and will be replayed.\n"
            "  - Unchecked: Only mouse clicks and key presses are captured.\n"
            "    (Note: This setting controls what's *recorded* for movement, which then affects replay.)\n\n"

            "Edit - Add Clicks (Button - View > Show Edit Clicks Section):\n"
            "  This feature allows you to add new mouse clicks to the end of the currently loaded or recorded sequence.\n"
            "  1. Ensure a recording is active (either newly made or loaded).\n"
            "  2. Click the 'Edit: Add Clicks' button.\n"
            "  3. The app will prompt you to 'Click screen for position...'. Click where you want the new clicks to occur.\n"
            "  4. An input field 'Count:' appears. Enter the number of times you want this click to be added.\n"
            "  5. Click 'Add These Clicks'. The specified number of left-button clicks will be appended to your recording.\n"
            "  6. You can cancel the process at various stages using the 'Cancel' buttons or by pressing ESC.\n\n"

            "----------------------------------------\n"
            "  Managing Your Recordings\n"
            "----------------------------------------\n"
            "Recording Name (Entry Field):\n"
            "  - Before saving a new recording, type a descriptive name for it here.\n\n"

            "Save (Button):\n"
            "  - After you've stopped a recording and named it, click 'Save' to store it for later use.\n\n"

            "Load/Delete (Dropdown & Buttons):\n"
            "  - Select a previously saved recording from the dropdown list.\n"
            "  - Load: Loads the selected recording. It's now ready to be played back or edited.\n"
            "  - Delete: Permanently removes the selected recording from your saved list (you'll be asked to confirm).\n\n"

            "----------------------------------------\n"
            "  Changing Global Keybinds (Options Menu)\n"
            "----------------------------------------\n"
            "Change shortcuts for Record, Playback, Exit, and AutoClick.\n"
            "  1. Go to the 'Options > Change Keybinds' menu at the top of the window.\n"
            "  2. Select the action you want to re-assign (e.g., Record).\n"
            "  3. The application will prompt you in the log area. Press and hold your new desired key(s) and then press 'Enter' to set the new keybind.\n\n"

            "----------------------------------------\n"
            "  Customizing Your View (View Menu)\n"
            "----------------------------------------\n"
            "Use the 'View' menu at the top to:\n"
            "  - Show Edit Clicks Section: Toggles the visibility of the 'Edit: Add Clicks' button area.\n"
            "  (Hiding these sections will also reduce the main window's height.)\n\n"

            "Enjoy using the recorder!"
        )
        messagebox.showinfo("Help - How to Use", help_text, parent=self.root)


    def start_listeners(self):
        self.log_to_bug_report("INFO - Attempting to start main input listeners...")
        try:
            self.listener_mouse = mouse.Listener(on_click=self.on_mouse_click, on_move=self.on_mouse_move, on_scroll=self.on_mouse_scroll)
            self.listener_keyboard = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
            self.listener_mouse.start()
            self.listener_keyboard.start()
            self.log_to_bug_report("INFO - Main input listeners started successfully.")
        except Exception as e:
            self.log_message(f"Error starting main listeners: {e}. Check permissions!")
            self.log_to_bug_report(f"ERROR - Starting main listeners: {e}. Check permissions!\n{traceback.format_exc()}")
            if hasattr(self, 'status_label'): self.status_label.config(text=f"ERROR: {e}")

    def on_mouse_click(self, x, y, button, pressed):
        if self.waiting_for_edit_click_position and pressed:
            if button == Button.left:
                self.edit_captured_click_x = x
                self.edit_captured_click_y = y
                self.waiting_for_edit_click_position = False
                self.log_message(f"ADD CLICKS MODE: Target position captured: ({x}, {y}).")
                self.log_to_bug_report(f"ACTION_DETAIL - Add Clicks: Position ({x},{y}) captured for edit.")
                self.root.after(0, self._update_ui_for_add_click_confirmation)
                return
            else:
                self.log_message("ADD CLICKS MODE: Position capture cancelled (non-left click).")
                self.log_to_bug_report("ACTION_DETAIL - Add Clicks: Position capture cancelled by non-left click.")
                self.cancel_add_click_mode()
                return

        if self.recording:
            button_name = button.name if hasattr(button, 'name') else str(button)
            event = ('mouse_click', x, y, button_name, pressed, time.time())
            self.recorded_events.append(event)

    def on_mouse_move(self, x, y):
        if self.recording and self.move_mouse:
            event = ('mouse_move', x, y, time.time())
            self.recorded_events.append(event)

    def on_mouse_scroll(self, x, y, dx, dy):
        if self.recording:
            event = ('mouse_scroll', x, y, dx, dy, time.time())
            self.recorded_events.append(event)

    def on_key_press(self, key):
        key_str = self._get_key_display_name(key)

        if self.waiting_for_edit_click_position and key != Key.esc:
            return

        if self.waiting_for_edit_click_position and key == Key.esc:
            self.log_to_bug_report("ACTION_DETAIL - Add Clicks: Position capture cancelled by ESC key press.")
            self.cancel_add_click_mode()
            return


        if self.recording and key_str in keybinds['record'] and self.current_keys.issubset(keybinds['record']):
            return

        if self.listening_for_keybind is not None:
            if key_str != 'enter':
                self.current_keys.add(key_str)
            action_type = self.listening_for_keybind
            msg = f"Press enter for {action_type}: {'+'.join(sorted(list(self.current_keys))).upper()}"
            if msg != self.last_log_message:
                self.log_message(msg)
                self.last_log_message = msg
            return

        if key_str not in self.current_keys:
            self.current_keys.add(key_str)

        if self.recording:
            event = ('key_press', key_str, time.time())
            self.recorded_events.append(event)


    def on_key_release(self, key):
        key_str = self._get_key_display_name(key)

        if self.is_editing_add_click_mode and key == Key.esc:
            self.log_to_bug_report("ACTION_DETAIL - Add Clicks: Mode cancelled by ESC key release.")
            self.cancel_add_click_mode()
            if key_str in self.current_keys: self.current_keys.remove(key_str)
            return

        if self.listening_for_keybind and key_str == 'enter':
            action = self.listening_for_keybind
            keys_str = '+'.join(sorted(list(self.current_keys))).upper() if self.current_keys else "NONE"
            if self.current_keys:
                keybinds[action] = set(self.current_keys)
                self.log_message(f"{action.capitalize()} keybind: {keys_str}")
                self.log_to_bug_report(f"ACTION_KEYBIND - Keybind for '{action}' set to: {keys_str} (Source: {self.last_action_source})")
            else:
                self.log_message(f"No keys for {action}. Old kept.")
                self.log_to_bug_report(f"INFO - Keybind for '{action}' setting cancelled (no keys). (Source: {self.last_action_source})")
            self.listening_for_keybind = None
            self.current_keys.clear()
            self.last_log_message = None
            self._save_settings()
            return

        if self.listening_for_keybind and key_str in self.current_keys:
            self.current_keys.remove(key_str)
            action_type = self.listening_for_keybind
            msg = f"Press enter for {action_type}: {'+'.join(sorted(list(self.current_keys))).upper()}"
            if not self.current_keys: msg = f"Press keybind for {action_type} & Enter."
            if msg != self.last_log_message: self.log_message(msg); self.last_log_message = msg

        if not (self.listening_for_keybind or self.is_editing_add_click_mode) and key_str in self.current_keys:
                 self.current_keys.remove(key_str)

        if self.is_editing_add_click_mode:
            if key_str in self.current_keys: self.current_keys.remove(key_str)
            return

        active_combo_check_keys = self.current_keys | {key_str}
        for action, combo_keys_set in keybinds.items():
            if key_str in combo_keys_set and combo_keys_set.issubset(active_combo_check_keys):
                if len(active_combo_check_keys) == len(combo_keys_set):
                    source = f"Keybind '{'+'.join(sorted(list(combo_keys_set)))}' for '{action}'"
                    if action == 'exit': self.handle_action("exit_app", source); return
                    elif action == 'record' and not self.playing_back: self.handle_action("toggle_recording", source); return
                    elif action == 'playback' and not self.recording: self.handle_action("toggle_playback", source); return
                    elif action == 'auto_click': self.handle_action("toggle_auto_click", source); return

        if self.recording:
            event = ('key_release', key_str, time.time())
            self.recorded_events.append(event)

    def log_message(self, msg):
        if hasattr(self, 'text_display') and self.text_display is not None:
            if self.text_display.winfo_exists():
                now = datetime.now()
                time_str = now.strftime("%I:%M:%S%p")
                clock_emoji = "\U0001F553"
                timestamped_msg = f"{clock_emoji}{time_str} {msg}"

                self.text_display.config(state=tk.NORMAL)
                self.text_display.insert(tk.END, timestamped_msg + "\n")
                self.text_display.see(tk.END)
                self.text_display.config(state=tk.DISABLED)

    def toggle_recording(self):
        if self.is_editing_add_click_mode: self.cancel_add_click_mode()
        if self.recording:
            self.recording = False; self.record_btn.config(text="● REC")
            msg = f"Recording stopped. {len(self.recorded_events)} events."
            self.log_message(msg)
        else:
            if self.playing_back or self.auto_clicking:
                msg = "Cannot record while other action active."
                self.log_message(msg)
                self.log_to_bug_report(f"WARNING - {msg} (Attempted by {self.last_action_source})")
                return
            self.recorded_events.clear()
            self.recording = True; self.record_btn.config(text="■ STOP")
            msg = "Recording started."
            self.log_message(msg)


    def toggle_playback(self):
        if self.is_editing_add_click_mode: self.cancel_add_click_mode()
        if self.playing_back:
            self.playing_back = False;
            if hasattr(self, 'play_btn') and self.play_btn.winfo_exists() and self.play_btn.cget('text') != "▶ PLAY":
                           self.play_btn.config(text="▶ PLAY")
                           source_info = self.last_action_source if self.last_action_source != "System" else "user action"
                           stop_message = f"Playback stopped by user (Trigger: {source_info})."
                           self.log_message(stop_message)
                           self.log_to_bug_report(f"ACTION_DETAIL - {stop_message}")
        else:
            if self.recording or self.auto_clicking:
                msg = "Cannot play back while other action active."
                self.log_message(msg)
                self.log_to_bug_report(f"WARNING - {msg} (Attempted by {self.last_action_source})")
                return
            if not self.recorded_events:
                msg = "No recorded events to play."
                self.log_message(msg)
                self.log_to_bug_report(f"WARNING - {msg} (Attempted by {self.last_action_source})")
                return
            self.playing_back = True; self.play_btn.config(text="■ STOP")
            self.log_message("Playback started...")
            self.log_to_bug_report(f"ACTION_DETAIL - Playback thread starting... (Source: {self.last_action_source})")
            self.playback_thread = threading.Thread(target=self.playback, daemon=True)
            self.playback_thread.start()

    def toggle_auto_click(self):
        if self.is_editing_add_click_mode: self.cancel_add_click_mode()
        if self.auto_clicking:
            self.auto_clicking = False; self.auto_click_btn.config(text="AutoClick")
            self.log_message("AutoClick stopped.")
            self.log_to_bug_report(f"ACTION_DETAIL - AutoClick stopped. (Source: {self.last_action_source})")
        else:
            if self.recording or self.playing_back:
                msg = "Cannot auto-click while other action active."
                self.log_message(msg)
                self.log_to_bug_report(f"WARNING - {msg} (Attempted by {self.last_action_source})")
                return
            self.auto_clicking = True; self.auto_click_btn.config(text="STOP Auto")
            self.log_message("AutoClick started.")
            self.log_to_bug_report(f"ACTION_DETAIL - AutoClick thread starting... (Source: {self.last_action_source})")
            self.auto_click_thread = threading.Thread(target=self.auto_click_loop, daemon=True)
            self.auto_click_thread.start()

    def validate_auto_click_interval_and_save(self, event=None):
        old_val_for_log = self.auto_click_interval_var.get()
        try:
            val = float(self.auto_click_interval_var.get())
            if val < 0:  # If it's negative
                self.auto_click_interval_var.set("0.0")
            # If val is 0 or positive, it's kept as is by not changing self.auto_click_interval_var yet.
            # If user types "0", val becomes 0.0. String variable remains "0" unless changed above.
        except ValueError:  # If not a valid float
            self.auto_click_interval_var.set("1.0")

        new_val_for_log = self.auto_click_interval_var.get()
        if old_val_for_log != new_val_for_log:
            self.log_to_bug_report(f"VALIDATION - Auto-click interval changed from '{old_val_for_log}' to '{new_val_for_log}'.")
            self._save_settings()


    def validate_inter_playback_delay_and_save(self, event=None):
        old_val = self.inter_playback_delay_seconds_var.get()
        try:
            val = float(old_val)
            if val < 0: self.inter_playback_delay_seconds_var.set("0.0")
        except ValueError: self.inter_playback_delay_seconds_var.set("1.0")
        if old_val != self.inter_playback_delay_seconds_var.get():
            self.log_to_bug_report(f"VALIDATION - Inter-playback delay changed from '{old_val}' to '{self.inter_playback_delay_seconds_var.get()}'.")
            self._save_settings()

    def _validate_and_save_loop_count(self, event=None):
        old_val = self.loop_count_var.get()
        try:
            val = int(old_val)
            if val <= 0 : self.loop_count_var.set("1")
        except ValueError:
            self.loop_count_var.set("1")
        if old_val != self.loop_count_var.get():
            self.log_to_bug_report(f"VALIDATION - Loop count changed from '{old_val}' to '{self.loop_count_var.get()}'.")
        self._save_settings()


    def _save_settings_on_interaction(self, event=None):
        self.log_to_bug_report(f"OPTION_CHANGE - UI option changed, saving settings.")
        self._save_settings()


    def set_move_mode(self):
        self.move_mouse = bool(self.move_var.get())
        self.log_to_bug_report(f"OPTION - Replay Movement (move_var) toggled to: {self.move_var.get()} -> move_mouse: {self.move_mouse}")
        self._save_settings()


    def start_listen_keybind(self, action):
        if self.is_editing_add_click_mode: self.cancel_add_click_mode()
        if self.listening_for_keybind:
            self.log_to_bug_report(f"INFO - Attempt to set keybind for '{action}' while already listening for another. (Source: {self.last_action_source})")
            return
        self.listening_for_keybind = action
        self.current_keys.clear()
        self.last_log_message = None
        msg = f"Press keybind for {action} & Enter."
        self.log_message(msg)
        self.log_to_bug_report(f"STATE - Listening for keybind for '{action}'. (Source: {self.last_action_source})")

    def update_playback_speed_label(self, *args):
        val = self.playback_speed_var.get()
        display_val = int(round(val))
        if display_val > 0: self.playback_speed_label.config(text=f"{display_val}x")
        elif display_val < 0: self.playback_speed_label.config(text=f"{1 + abs(display_val)}x Slower")
        else: self.playback_speed_label.config(text="0x (Paused)")

    def playback(self):
        loop_enabled = self.loop_var.get() == 1
        try:
            loop_count_str = self.loop_count_var.get()
            loop_count = int(loop_count_str)
            loop_count = max(1, loop_count)
        except ValueError:
            loop_count = 1
            self.log_to_bug_report(f"PLAYBACK_DETAIL - Loop count invalid ('{loop_count_str}'), defaulting to 1. Loop enabled: {loop_enabled}")

        loop_iterations = loop_count if loop_enabled else 1

        for i in range(loop_iterations):
            self.log_to_bug_report(f"PLAYBACK_DETAIL - Starting loop iteration {i+1} of {loop_iterations}.")
            if not self.playing_back:
                self.log_to_bug_report("PLAYBACK_DETAIL - Playback flag became false, breaking loop.")
                break
            start_time = prev_time = None
            for event_idx, event in enumerate(self.recorded_events):
                if not self.playing_back:
                    self.log_to_bug_report(f"PLAYBACK_DETAIL - Playback flag became false during event processing (event {event_idx+1}), breaking inner loop.")
                    break
                event_type, timestamp = event[0], event[-1]
                if self.replay_with_original.get() == 1:
                    if start_time is None: start_time = prev_time = timestamp
                    else:
                        time_to_wait = timestamp - prev_time
                        speed = self.playback_speed_var.get()
                        eff_wait = 0
                        if speed > 0: eff_wait = max(0.0001, time_to_wait / speed)
                        elif speed < 0: eff_wait = time_to_wait * (1 + abs(speed))
                        else:
                            self.log_to_bug_report("PLAYBACK_DETAIL - Playback paused (speed 0x).")
                            while self.playing_back and self.playback_speed_var.get() == 0: time.sleep(0.05)
                            if not self.playing_back:
                                self.log_to_bug_report("PLAYBACK_DETAIL - Playback stopped during pause.")
                                break
                            self.log_to_bug_report("PLAYBACK_DETAIL - Playback resumed from pause.")
                            prev_time = timestamp; continue
                        if eff_wait > 0:
                            sleep_end_time = time.time() + eff_wait
                            while time.time() < sleep_end_time:
                                if not self.playing_back: break
                                time.sleep(min(0.01, sleep_end_time - time.time()) if sleep_end_time - time.time() > 0 else 0)
                        prev_time = timestamp
                else: time.sleep(0.001)
                if not self.playing_back: break

                try:
                    if event_type == 'mouse_click':
                        _, x, y, btn_data, pressed, _ = event
                        btn_play = None
                        if isinstance(btn_data, dict) and '__button__' in btn_data: btn_play = getattr(Button,btn_data['__button__'],None)
                        elif isinstance(btn_data, str): btn_play = getattr(Button, btn_data, None)
                        if btn_play is None: self.log_to_bug_report(f"PLAYBACK_WARN - Unknown button data '{btn_data}' for event {event_idx+1}."); continue
                        mouse_controller.position = (x,y)
                        if pressed: mouse_controller.press(btn_play)
                        else: mouse_controller.release(btn_play)
                    elif event_type == 'mouse_move' and self.move_mouse:
                        _, x, y, _ = event; mouse_controller.position = (x,y)
                    elif event_type == 'mouse_scroll':
                        _, x, y, dx, dy, _ = event; mouse_controller.position = (x,y); mouse_controller.scroll(dx,dy)
                    elif event_type == 'key_press':
                        _, key_data, _ = event; key_play = None
                        if hasattr(Key, key_data): key_play = getattr(Key, key_data)
                        elif isinstance(key_data, str) and len(key_data)>0: key_play = key_data
                        if key_play is None: self.log_to_bug_report(f"PLAYBACK_WARN - Unknown key press data '{key_data}' for event {event_idx+1}."); continue
                        keyboard_controller.press(key_play)
                    elif event_type == 'key_release':
                        _, key_data, _ = event; key_play = None
                        if hasattr(Key, key_data): key_play = getattr(Key, key_data)
                        elif isinstance(key_data, str) and len(key_data)>0: key_play = key_data
                        if key_play is None: self.log_to_bug_report(f"PLAYBACK_WARN - Unknown key release data '{key_data}' for event {event_idx+1}."); continue
                        keyboard_controller.release(key_play)
                except Exception as e:
                    err_msg = f"Playback error on event {event_idx+1} ({event_type}): {e}"
                    self.log_message(err_msg)
                    self.log_to_bug_report(f"ERROR - {err_msg}\n{traceback.format_exc()}")
                    if self.playing_back:
                        self.root.after(0, lambda err=e: self.handle_playback_error(err))
                    break

            if not self.playing_back:
                self.log_to_bug_report("PLAYBACK_DETAIL - Playback stopped, exiting outer loop.")
                break
            if loop_enabled and self.inter_playback_delay_var.get() == 1 and i < loop_iterations - 1:
                try:
                    delay_s = float(self.inter_playback_delay_seconds_var.get())
                    if delay_s > 0:
                        delay_log_msg = f"Inter-loop delay: Waiting {delay_s}s..."
                        self.log_to_bug_report(f"PLAYBACK_DETAIL - {delay_log_msg}")
                        self.log_message(delay_log_msg)
                        end_time = time.time() + delay_s
                        while time.time() < end_time:
                            if not self.playing_back: self.log_to_bug_report("PLAYBACK_DETAIL - Stopped during inter-loop delay."); break
                            time.sleep(0.05)
                        if not self.playing_back: break
                except ValueError:
                    self.log_to_bug_report(f"PLAYBACK_WARN - Invalid inter-loop delay value '{self.inter_playback_delay_seconds_var.get()}'. Skipping.")

        if self.playing_back:
            self.playing_back = False
            if hasattr(self, 'play_btn') and self.play_btn.winfo_exists(): self.play_btn.config(text="▶ PLAY")
            self.log_message("Playback finished.")
            self.log_to_bug_report("ACTION_DETAIL - Playback finished naturally.")
        elif hasattr(self, 'play_btn') and self.play_btn.winfo_exists() and self.play_btn.cget('text') != "▶ PLAY":
               self.play_btn.config(text="▶ PLAY")


    def handle_playback_error(self, error_exception):
        self.log_to_bug_report(f"PLAYBACK_ERROR_HANDLER - Error reported: {error_exception}")
        if messagebox.askyesno("Playback Error", f"Error during playback: {error_exception}\nStop playback?", parent=self.root):
            self.log_to_bug_report("PLAYBACK_ERROR_HANDLER - User chose to stop playback after error.")
            if self.playing_back:
                self.playing_back = False
                if hasattr(self, 'play_btn') and self.play_btn.winfo_exists(): self.play_btn.config(text="▶ PLAY")
                self.log_message("Playback stopped due to error.")
        else:
            self.log_to_bug_report("PLAYBACK_ERROR_HANDLER - User chose to continue (or ignore) after error. Playback likely already stopped.")


    def auto_click_loop(self):
        while self.auto_clicking:
            try:
                interval_str = self.auto_click_interval_var.get()
                interval = float(interval_str)
                # Validation in validate_auto_click_interval_and_save ensures interval >= 0.0
            except ValueError:
                # This case should ideally not be hit if validation on input works correctly
                interval = 1.0 # Default fallback
                self.log_to_bug_report(f"AUTOCLICK_WARN - Invalid interval string '{interval_str}' in loop (should be pre-validated), defaulting to {interval}s.")

            try:
                mouse_controller.press(Button.left)
                mouse_controller.release(Button.left)
            except Exception as e:
                self.log_to_bug_report(f"AUTOCLICK_ERROR - Error during click: {e}\n{traceback.format_exc()}")
                self.auto_clicking = False
                if hasattr(self, 'auto_click_btn') and self.auto_click_btn.winfo_exists():
                    self.root.after(0, lambda: self.auto_click_btn.config(text="AutoClick"))
                self.log_message("AutoClick stopped due to error.")
                self.log_to_bug_report("ACTION_DETAIL - AutoClick stopped due to error during click.")
                break

            time.sleep(interval) # If interval is 0.0, time.sleep(0.0) will be called.

    def exit_app(self):
        if self.is_editing_add_click_mode: self.cancel_add_click_mode()

        self.log_to_bug_report("INFO - Normal application exit process started.")
        self._save_settings()
        self._save_recordings()
        self.log_message("Settings saved. Exiting.")

        if self.listener_mouse and self.listener_mouse.running:
            self.listener_mouse.stop()
            self.log_to_bug_report("INFO - Main mouse listener stopped.")
        if self.listener_keyboard and self.listener_keyboard.running:
            self.listener_keyboard.stop()
            self.log_to_bug_report("INFO - Main keyboard listener stopped.")

        self.log_to_bug_report("INFO - Application shutting down gracefully.")
        self.root.quit()


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = RecorderApp(root)
        app.log_to_bug_report("INFO - Main Tkinter loop starting.")
        root.after(150, app.start_listeners)
        root.mainloop()
        if hasattr(app, 'log_to_bug_report'):
            app.log_to_bug_report("INFO - Main Tkinter loop finished.")
    except SystemExit:
        if 'app' in locals() and hasattr(app, 'log_to_bug_report'):
            app.log_to_bug_report("INFO - Application exited via SystemExit.")
        else:
            try:
                # Check if BUGREPORT_FILE is defined, if not, use a default name or skip
                bug_report_path = BUGREPORT_FILE if 'BUGREPORT_FILE' in globals() else 'bugreport_emergency.txt'
                with open(bug_report_path, 'a', encoding='utf-8') as f: f.write(f"{datetime.now().strftime('%I:%M:%S%p')} SystemExit occurred before full app log init or after app destruction.\n")
            except: pass
        pass