import customtkinter as ctk
import time
import datetime
import json
import os
import threading
import pynput.mouse
import pynput.keyboard
from typing import Optional, List, Dict, Any
import traceback
import sys
import math
import collections

# --- Configuration ---
APP_NAME = "activitytracker3000"
DATA_FILE = "mouse_activity_log.json"
ACTIVITY_CHECK_INTERVAL = 0.1
INITIAL_INACTIVITY_TIMEOUT = 5.0
LONG_INACTIVITY_THRESHOLD = 600.0
INITIAL_FOCUS_MINUTES = 25
INITIAL_BREAK_MINUTES = 5

APP_FONT_FAMILY = "helvetica"
BASE_WINDOW_WIDTH = 800
BASE_WINDOW_HEIGHT = 630 # Adjusted slightly
# Font sizes
BASE_FONT_SIZE_TOTAL_SESSION_TIME_RIGHT = 14 # For bottom right
BASE_FONT_SIZE_CLOCK_RIGHT = 35          # For bottom right
BASE_FONT_SIZE_PROMINENT_CURRENT_STATS = 40
BASE_FONT_SIZE_PROMINENT_STATS_SUBTITLE = 16
BASE_FONT_SIZE_GRID_COUNTERS = 20
BASE_FONT_SIZE_GRID_SUBTITLES = 12
BASE_FONT_SIZE_FOCUS_BREAK_TIMER = 28
BASE_FONT_SIZE_FOCUS_BREAK_STATUS = 12
BASE_FONT_SIZE_SECTION_TITLES = 14
BASE_FONT_SIZE_BUTTONS = 9
BASE_FONT_SIZE_SETTINGS_LABELS = 9
BASE_FONT_SIZE_SETTINGS_ENTRIES = 10
BASE_FONT_SIZE_LOG_TITLE = 13
BASE_FONT_SIZE_FOCUS_HISTORY_TEXT = 12


MIN_FONT_SIZE_TOTAL_SESSION_TIME_RIGHT = 8
MIN_FONT_SIZE_CLOCK_RIGHT = 10
MIN_FONT_SIZE_PROMINENT_CURRENT_STATS = 24
MIN_FONT_SIZE_PROMINENT_STATS_SUBTITLE = 10
MIN_FONT_SIZE_GRID_COUNTERS = 10
MIN_FONT_SIZE_GRID_SUBTITLES = 8
MIN_FONT_SIZE_FOCUS_BREAK_TIMER = 14
MIN_FONT_SIZE_FOCUS_BREAK_STATUS = 8
MIN_FONT_SIZE_SECTION_TITLES = 10
MIN_FONT_SIZE_BUTTONS = 8
MIN_FONT_SIZE_SETTINGS_LABELS = 8
MIN_FONT_SIZE_SETTINGS_ENTRIES = 8
MIN_FONT_SIZE_FOCUS_HISTORY_TEXT = 8


BASE_FONT_SIZE_EFFECTIVENESS_VALUE = 48
MIN_FONT_SIZE_EFFECTIVENESS_VALUE = 18
BASE_FONT_SIZE_EFFECTIVENESS_TITLE = BASE_FONT_SIZE_SECTION_TITLES


COLOR_WINDOW_BG="#2a2a2a"; COLOR_MAIN_CONTENT_BG="#1D1D1D"; COLOR_BORDER="#1D1D1D"
BORDER_THICKNESS=15; COLOR_TEXT_PRIMARY="#F0F0F0"; COLOR_TEXT_SECONDARY="#A9A9A9"
COLOR_TEXT_INACTIVE="#FF3B30"; COLOR_CLOCK_TEXT="#E8D85C"; COLOR_ACCENT_ACTIVE_MOUSE="#30D158"
COLOR_TIMER_FOCUS="#28C740"; COLOR_TIMER_BREAK="#00A9FF"; COLOR_BUTTON_FG="#2E2E2E"; COLOR_BUTTON_HOVER="#3F3F3F"
COLOR_BUTTON_TEXT=COLOR_TEXT_PRIMARY; CONSOLE_BG="#1a1a1a"; CONSOLE_FG="#a0a0a0"
CONSOLE_FONT_SIZE=8; MAX_LOG_LINES=150; EFFECTIVENESS_BAR_HEIGHT=6
EFFECTIVENESS_BAR_LOW_COLOR = COLOR_TEXT_INACTIVE
FOCUS_HISTORY_BG = CONSOLE_BG
FOCUS_HISTORY_FG = CONSOLE_FG
# --- End Configuration ---

_current_inactivity_timeout = INITIAL_INACTIVITY_TIMEOUT

app_state = {
    "last_mouse_position": None, "mouse_last_pos_for_distance": None,
    "mouse_total_distance_today": 0.0, "keystrokes_today": 0,
    "last_movement_time": time.time(), "last_keyboard_activity_time": time.time(),
    "total_active_seconds_today": 0.0, "total_idle_seconds_today": 0.0,
    "max_idle_seconds_today": 0.0, "max_active_seconds_today": 0.0,
    "current_activity_start_time": time.time(),
    "current_idle_start_time": None,
    "last_activity_duration": 0.0,
    "last_inactivity_duration": 0.0,
    "current_day_string": datetime.date.today().isoformat(),
    "running": True, "prev_overall_active_state": False,
    "last_activity_time": time.time(),
    "focus_duration_seconds": INITIAL_FOCUS_MINUTES * 60,
    "break_duration_seconds": INITIAL_BREAK_MINUTES * 60,
    "timer_mode": "focus",
    "timer_seconds_remaining": INITIAL_FOCUS_MINUTES * 60,
    "mouse_clicks_today": 0,
    "current_focus_active_seconds": 0.0,
    "focus_session_log": collections.deque(maxlen=5),
}
state_lock = threading.Lock()

def format_hms_string(s: float) -> str:
    s=max(0,s); h=s//3600; m=(s%3600)//60; s%=60; return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
def format_ms_string(s: float) -> str:
    s=max(0,s); m=s//60; s%=60; return f"{int(m):02d}:{int(s):02d}"

_app_instance_ref = None

def on_move(x,y):
    global app_state, _app_instance_ref
    if _app_instance_ref and (_app_instance_ref.session_globally_paused or _app_instance_ref.timed_break_active): return
    with state_lock:
        now=time.time();pos=(x,y)
        if app_state["mouse_last_pos_for_distance"] is not None:
            px,py=app_state["mouse_last_pos_for_distance"];app_state["mouse_total_distance_today"]+=math.sqrt((x-px)**2+(y-py)**2)
        app_state["mouse_last_pos_for_distance"]=pos
        app_state.update({"last_mouse_position":pos,"last_movement_time":now,"last_activity_time":now})

def on_key_press(key):
    global app_state, _app_instance_ref
    if _app_instance_ref and (_app_instance_ref.session_globally_paused or _app_instance_ref.timed_break_active): return
    with state_lock:
        app_state["keystrokes_today"]+=1
        app_state.update({"last_keyboard_activity_time":time.time(),"last_activity_time":time.time()})

def on_click(x, y, button, pressed):
    global app_state, _app_instance_ref
    if _app_instance_ref and (_app_instance_ref.session_globally_paused or _app_instance_ref.timed_break_active): return
    if pressed:
        with state_lock:
            app_state["mouse_clicks_today"] += 1
            app_state.update({"last_activity_time": time.time()})

def load_daily_data():
    global app_state
    today_str = datetime.date.today().isoformat()
    default_data = {"active_seconds":0.0, "idle_seconds":0.0, "max_idle_seconds":0.0,
                    "max_active_seconds":0.0, "mouse_total_distance":0.0, "keystrokes":0,
                    "mouse_clicks":0, "last_activity_duration":0.0, "last_inactivity_duration":0.0}
    data_today = default_data.copy(); full_data = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE,'r')as f: content=f.read()
            if content:full_data=json.loads(content)
        except Exception as e: print(f"Warning loading {DATA_FILE}: {e}")
    raw_today = full_data.get(today_str)
    if isinstance(raw_today, dict):
        for key_ in data_today:
            if key_ in ["keystrokes", "mouse_clicks"]: data_today[key_] = int(raw_today.get(key_,0))
            else: data_today[key_] = float(raw_today.get(key_,0.0))
    elif isinstance(raw_today,(float,int)): data_today["active_seconds"]=float(raw_today)
    with state_lock:
        app_state.update({
            "current_day_string":today_str,
            "total_active_seconds_today":data_today["active_seconds"],"total_idle_seconds_today":data_today["idle_seconds"],
            "max_idle_seconds_today":data_today["max_idle_seconds"],"max_active_seconds_today":data_today["max_active_seconds"],
            "mouse_total_distance_today":data_today["mouse_total_distance"],"keystrokes_today":data_today["keystrokes"],
            "mouse_clicks_today": data_today["mouse_clicks"],
            "last_activity_duration": data_today["last_activity_duration"],"last_inactivity_duration": data_today["last_inactivity_duration"],
            "current_activity_start_time":time.time(),"current_idle_start_time": None,
        })

def save_daily_data():
    global app_state; full_data={}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE,'r')as f:content=f.read()
            if content:full_data=json.loads(content)
        except Exception:full_data={}
    with state_lock:
        day_s=app_state["current_day_string"]
        data_to_save={k:round(app_state[k],2)if isinstance(app_state[k],float)else app_state[k] for k in [
            "total_active_seconds_today","total_idle_seconds_today","max_idle_seconds_today",
            "max_active_seconds_today","mouse_total_distance_today","keystrokes_today", "mouse_clicks_today",
            "last_activity_duration","last_inactivity_duration"]}
    full_data[day_s]=data_to_save
    try:
        with open(DATA_FILE,'w')as f:json.dump(full_data,f,indent=4)
    except Exception as e:print(f"Error writing to {DATA_FILE}: {e}")

def add_log_message(app_instance,message: str):
    if not isinstance(app_instance,ctk.CTk)or not hasattr(app_instance,'event_log_console')or not app_instance.event_log_console.winfo_exists():
        print(f"Event Log Console not ready: {message}");return
    log_text=f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}\n"
    def _update():
        try:
            if not app_instance.event_log_console.winfo_exists():return
            app_instance.event_log_console.configure(state="normal")
            lines=[l for l in app_instance.event_log_console.get("1.0","end-1c").split('\n')if l]
            if len(lines)>=MAX_LOG_LINES:lines=lines[-(MAX_LOG_LINES-1):]
            app_instance.event_log_console.delete("1.0","end");app_instance.event_log_console.insert("1.0",'\n'.join(lines+[log_text.strip()])+'\n')
            app_instance.event_log_console.see("end");app_instance.event_log_console.configure(state="disabled")
        except Exception as e:print(f"Error GUI log: {e}")
    if app_instance.winfo_exists():app_instance.after(0,_update)

class DominantBorderHubApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        global _app_instance_ref
        _app_instance_ref = self

        self.title(APP_NAME); self.geometry(f"{BASE_WINDOW_WIDTH}x{BASE_WINDOW_HEIGHT}")
        self.minsize(850, BASE_WINDOW_HEIGHT); ctk.set_appearance_mode("Dark")
        self.configure(fg_color=COLOR_WINDOW_BG)

        self.app_launch_time = time.time()
        self.session_globally_paused = False
        self.session_pause_start_time = None
        self.total_session_time_actively_paused = 0.0
        self.timed_break_active = False
        self.timed_break_duration_seconds = 0 
        self.timed_break_end_time = None
        self.timed_break_initiated_pause = False
        self._color_tags_defined = False

        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
            if os.path.exists(icon_path): self.iconbitmap(icon_path)
            else: print("Icon file not found:", icon_path)
        except Exception as e: print(f"Icon error: {e}")

        load_daily_data(); self._init_fonts()

        self.main_split=ctk.CTkFrame(self,fg_color="transparent")
        self.main_split.pack(fill="both",expand=True,padx=15,pady=15)
        self.main_split.grid_columnconfigure(0,weight=2);self.main_split.grid_columnconfigure(1,weight=3)
        self.main_split.grid_rowconfigure(0,weight=1)

        self.main_content_frame=ctk.CTkFrame(self.main_split,fg_color=COLOR_MAIN_CONTENT_BG,border_color=COLOR_BORDER,border_width=BORDER_THICKNESS,corner_radius=0)
        self.main_content_frame.grid(row=0,column=0,sticky="nsew",padx=(0,7))
        self.main_content_frame.grid_columnconfigure(0,weight=1)
        # Adjusted row config for left panel (main_content_frame) - reduced minsize values
        self.main_content_frame.grid_rowconfigure(0, weight=0, minsize=20)  # Timed Break Status (was top bar)
        self.main_content_frame.grid_rowconfigure(1, weight=1, minsize=40)  # Effectiveness
        self.main_content_frame.grid_rowconfigure(2, weight=1, minsize=60)  # Prominent Stats
        self.main_content_frame.grid_rowconfigure(3, weight=2, minsize=140) # Compact Stats & Controls

        self._create_timed_break_status_section() # Was part of _create_top_bar_section
        # self._create_clock_section() # Removed
        self._create_effectiveness_section()
        self._create_prominent_current_stats_section()
        self._create_compact_stats_grid_section()
        self._create_right_panel_section()

        add_log_message(self,"App starting...");self.bind("<Configure>",self.on_window_resize_debounced)
        self._resize_debounce_timer=None
        self.start_mouse_listener();self.start_keyboard_listener();self.start_tracking_loop()
        self.protocol("WM_DELETE_WINDOW",self.on_closing)
        self._update_pause_button_states()
        self.update_gui_display();self.after(250,self.on_window_resize)
        add_log_message(self,"App started.")

    def _init_fonts(self):
        self.font_total_session_time_right = (APP_FONT_FAMILY, BASE_FONT_SIZE_TOTAL_SESSION_TIME_RIGHT, "bold") # New
        self.font_clock_right = (APP_FONT_FAMILY, BASE_FONT_SIZE_CLOCK_RIGHT, "bold") # New
        self.font_prominent_current_stats = (APP_FONT_FAMILY, BASE_FONT_SIZE_PROMINENT_CURRENT_STATS, "bold")
        self.font_prominent_stats_subtitle = (APP_FONT_FAMILY, BASE_FONT_SIZE_PROMINENT_STATS_SUBTITLE, "normal")
        self.font_grid_counters=(APP_FONT_FAMILY,BASE_FONT_SIZE_GRID_COUNTERS,"bold")
        self.font_grid_subtitles=(APP_FONT_FAMILY,BASE_FONT_SIZE_GRID_SUBTITLES,"normal")
        self.font_focus_break_timer_value=(APP_FONT_FAMILY,BASE_FONT_SIZE_FOCUS_BREAK_TIMER,"bold")
        self.font_focus_break_status=(APP_FONT_FAMILY,BASE_FONT_SIZE_FOCUS_BREAK_STATUS,"bold")
        self.font_section_titles=(APP_FONT_FAMILY,BASE_FONT_SIZE_SECTION_TITLES,"bold")
        self.font_buttons=(APP_FONT_FAMILY,BASE_FONT_SIZE_BUTTONS,"bold")
        self.font_settings_labels=(APP_FONT_FAMILY,BASE_FONT_SIZE_SETTINGS_LABELS,"normal")
        self.font_settings_entries=(APP_FONT_FAMILY,BASE_FONT_SIZE_SETTINGS_ENTRIES,"normal")
        self.font_effectiveness_value=(APP_FONT_FAMILY,BASE_FONT_SIZE_EFFECTIVENESS_VALUE,"bold")
        self.font_effectiveness_title=(APP_FONT_FAMILY,BASE_FONT_SIZE_EFFECTIVENESS_TITLE,"bold")
        self.font_log_title = (APP_FONT_FAMILY, BASE_FONT_SIZE_LOG_TITLE, "bold")
        self.font_focus_history_text = (APP_FONT_FAMILY, BASE_FONT_SIZE_FOCUS_HISTORY_TEXT)
        self.font_event_log_console = (APP_FONT_FAMILY, CONSOLE_FONT_SIZE)

    def _create_timed_break_status_section(self): # Renamed from _create_top_bar_section
        # This frame is now just for the timed break status, which remains at the top of the left panel.
        status_frame = ctk.CTkFrame(self.main_content_frame, fg_color="transparent")
        status_frame.grid(row=0, column=0, pady=(5,0), padx=15, sticky="new") # Reduced top padding
        status_frame.grid_columnconfigure(0, weight=1)
        
        self.timed_break_status_label = ctk.CTkLabel(status_frame, text="", 
                                                     font=(APP_FONT_FAMILY, BASE_FONT_SIZE_BUTTONS-1, "bold"), # Smaller font
                                                     text_color=COLOR_TEXT_INACTIVE)
        self.timed_break_status_label.pack(pady=(0,2), fill="x")


    def _create_effectiveness_section(self):
        frame=ctk.CTkFrame(self.main_content_frame,fg_color="transparent")
        frame.grid(row=1,column=0,pady=(0,1),padx=15,sticky="nsew") # Removed top padding
        self.effectiveness_title_label=ctk.CTkLabel(frame,text="SESSION EFFECTIVENESS",font=self.font_effectiveness_title,text_color=COLOR_TEXT_SECONDARY); self.effectiveness_title_label.pack(pady=(0,1))
        self.effectiveness_value_label=ctk.CTkLabel(frame,text="N/A",font=self.font_effectiveness_value,text_color=COLOR_TEXT_PRIMARY); self.effectiveness_value_label.pack(pady=(0,1))
        self.effectiveness_bar_bg=ctk.CTkFrame(frame,fg_color="#404040",height=EFFECTIVENESS_BAR_HEIGHT+4,corner_radius=EFFECTIVENESS_BAR_HEIGHT//2); self.effectiveness_bar_bg.pack(fill="x",padx=30,pady=(0,1))
        self.effectiveness_bar=ctk.CTkFrame(self.effectiveness_bar_bg,fg_color=EFFECTIVENESS_BAR_LOW_COLOR,height=EFFECTIVENESS_BAR_HEIGHT,width=0,corner_radius=(EFFECTIVENESS_BAR_HEIGHT//2)-1); self.effectiveness_bar.place(x=2,y=2,relwidth=0)

    def _create_prominent_current_stats_section(self):
        frame = ctk.CTkFrame(self.main_content_frame, fg_color="transparent")
        frame.grid(row=2, column=0, pady=(1,0), padx=15, sticky="nsew") # Minimized top padding
        frame.grid_columnconfigure((0,1), weight=1)
        active_frame = ctk.CTkFrame(frame, fg_color="transparent")
        active_frame.grid(row=0, column=0, padx=5, pady=2, sticky="nsew")
        self.current_active_title_label = ctk.CTkLabel(active_frame, text="CURRENT ACTIVE", font=self.font_prominent_stats_subtitle, text_color=COLOR_TEXT_SECONDARY)
        self.current_active_title_label.pack(pady=(0,1))
        self.current_active_val_label = ctk.CTkLabel(active_frame, text="00:00:00", font=self.font_prominent_current_stats, text_color=COLOR_TEXT_PRIMARY)
        self.current_active_val_label.pack()
        idle_frame = ctk.CTkFrame(frame, fg_color="transparent")
        idle_frame.grid(row=0, column=1, padx=5, pady=2, sticky="nsew")
        self.current_idle_title_label = ctk.CTkLabel(idle_frame, text="CURRENT IDLE", font=self.font_prominent_stats_subtitle, text_color=COLOR_TEXT_SECONDARY)
        self.current_idle_title_label.pack(pady=(0,1))
        self.current_idle_val_label = ctk.CTkLabel(idle_frame, text="00:00:00", font=self.font_prominent_current_stats, text_color=COLOR_TEXT_PRIMARY)
        self.current_idle_val_label.pack()

    def _create_compact_stats_grid_section(self):
        frame=ctk.CTkFrame(self.main_content_frame,fg_color="transparent")
        frame.grid(row=3,column=0,pady=(0,2),padx=15,sticky="nsew") # Adjusted row
        frame.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(frame,text="OTHER DAILY STATS",font=self.font_section_titles,text_color=COLOR_TEXT_SECONDARY).pack(pady=(0,2))
        
        grid=ctk.CTkFrame(frame,fg_color="transparent");grid.pack(fill="x",expand=True,padx=10)
        grid.grid_columnconfigure((0,1,2),weight=1)
        for i in range(3): grid.grid_rowconfigure(i, weight=1)
        def _cell(r,c,title,attr,is_time=True):
            cell_f=ctk.CTkFrame(grid,fg_color="transparent");cell_f.grid(row=r,column=c,padx=1,pady=1,sticky="nsew")
            cell_f.grid_rowconfigure(0,weight=1); cell_f.grid_rowconfigure(1,weight=1); cell_f.grid_columnconfigure(0,weight=1)
            title_label=ctk.CTkLabel(cell_f,text=title,font=self.font_grid_subtitles,text_color=COLOR_TEXT_SECONDARY)
            title_label.grid(row=0,column=0,sticky="s",pady=(0,0))
            val_lbl=ctk.CTkLabel(cell_f,text="00:00:00"if is_time else"0",font=self.font_grid_counters,text_color=COLOR_TEXT_PRIMARY)
            val_lbl.grid(row=1,column=0,sticky="n",pady=(0,0))
            setattr(self,f"{attr}_grid_title",title_label); setattr(self,f"{attr}_grid_val",val_lbl)
        _cell(0,0,"TOTAL ACTIVE","total_active_today"); _cell(0,1,"MAX ACTIVE","max_active_today"); _cell(0,2,"PREV. ACTIVE SPELL","prev_active_spell")
        _cell(1,0,"TOTAL IDLE","total_idle_today"); _cell(1,1,"MAX IDLE","max_idle_today"); _cell(1,2,"PREV. IDLE SPELL","prev_idle_spell")
        _cell(2,0,"MOUSE DIST. (px)","mouse_dist",False); _cell(2,1,"KEYSTROKES","keystrokes",False); 
        clicks_cell_f = ctk.CTkFrame(grid, fg_color="transparent"); clicks_cell_f.grid(row=2, column=2, padx=1, pady=1, sticky="nsew")
        clicks_cell_f.grid_rowconfigure(0,weight=1); clicks_cell_f.grid_rowconfigure(1,weight=1); clicks_cell_f.grid_columnconfigure(0,weight=1)
        self.mouse_clicks_grid_title = ctk.CTkLabel(clicks_cell_f, text="MOUSE CLICKS", font=self.font_grid_subtitles, text_color=COLOR_TEXT_SECONDARY)
        self.mouse_clicks_grid_title.grid(row=0, column=0, sticky="s")
        self.mouse_clicks_grid_val = ctk.CTkLabel(clicks_cell_f, text="0", font=self.font_grid_counters, text_color=COLOR_TEXT_PRIMARY)
        self.mouse_clicks_grid_val.grid(row=1, column=0, sticky="n")

        control_buttons_frame = ctk.CTkFrame(frame, fg_color="transparent")
        control_buttons_frame.pack(pady=(4, 3), padx=5, fill="x", expand=False)
        control_buttons_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="group_buttons_col")

        grouped_btn_style = {"font": self.font_buttons, "corner_radius": 4, "height": 26,
                             "text_color": COLOR_BUTTON_TEXT, "border_width": 1, "border_color": "#444",
                             "fg_color": COLOR_BUTTON_FG, "hover_color": COLOR_BUTTON_HOVER}

        self.reset_activity_button = ctk.CTkButton(control_buttons_frame, text="RESET STATS", command=self.reset_daily_activity_counter, **grouped_btn_style)
        self.reset_activity_button.grid(row=0, column=0, padx=2, pady=2, sticky="ew")

        self.pause_session_button = ctk.CTkButton(control_buttons_frame, text="PAUSE SESSION", command=self.manual_pause_session, **grouped_btn_style)
        self.pause_session_button.grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        
        self.continue_session_button = ctk.CTkButton(control_buttons_frame, text="CONTINUE", command=self.manual_continue_session, **grouped_btn_style)
        self.continue_session_button.grid(row=0, column=2, padx=2, pady=2, sticky="ew")

        self.add_five_min_break_button = ctk.CTkButton(control_buttons_frame, text="ADD +5MIN BREAK", command=self.add_or_start_5_min_break, **grouped_btn_style)
        self.add_five_min_break_button.grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        
        self.pause_thirty_min_button = ctk.CTkButton(control_buttons_frame, text="PAUSE 30 MIN", command=lambda: self.start_timed_break(30 * 60, is_extendable=False), **grouped_btn_style)
        self.pause_thirty_min_button.grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        self.pause_one_hour_button = ctk.CTkButton(control_buttons_frame, text="PAUSE 60 MIN", command=lambda: self.start_timed_break(60 * 60, is_extendable=False), **grouped_btn_style)
        self.pause_one_hour_button.grid(row=1, column=2, padx=2, pady=2, sticky="ew")

    def _create_right_panel_section(self):
        right_panel = ctk.CTkFrame(self.main_split, fg_color=COLOR_MAIN_CONTENT_BG, border_color=COLOR_BORDER, border_width=BORDER_THICKNESS, corner_radius=0)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(8,0))
        right_panel.grid_columnconfigure(0, weight=1)
        # Row configuration for the right panel
        row_idx = 0
        right_panel.grid_rowconfigure(row_idx, weight=0, minsize=30); row_idx+=1 # Timer Title
        right_panel.grid_rowconfigure(row_idx, weight=0, minsize=50); row_idx+=1 # Timer Display
        right_panel.grid_rowconfigure(row_idx, weight=0, minsize=30); row_idx+=1 # Settings Grid
        right_panel.grid_rowconfigure(row_idx, weight=0, minsize=30); row_idx+=1 # Apply Buttons
        right_panel.grid_rowconfigure(row_idx, weight=0, minsize=15); row_idx+=1 # Separator space
        right_panel.grid_rowconfigure(row_idx, weight=0, minsize=30); row_idx+=1 # Focus History Title
        right_panel.grid_rowconfigure(row_idx, weight=4); row_idx+=1 # Focus History Textbox
        right_panel.grid_rowconfigure(row_idx, weight=0, minsize=30); row_idx+=1 # Event Log Title
        right_panel.grid_rowconfigure(row_idx, weight=2); row_idx+=1 # Event Log Textbox
        right_panel.grid_rowconfigure(row_idx, weight=0, minsize=15); row_idx+=1 # Separator for time
        right_panel.grid_rowconfigure(row_idx, weight=0, minsize=40); row_idx+=1 # Time Info (Session + Current)


        row_idx = 0 # Reset for placing elements
        ctk.CTkLabel(right_panel, text="FOCUS/BREAK TIMER", font=self.font_section_titles, text_color=COLOR_TEXT_SECONDARY).grid(row=row_idx, column=0, pady=(10,0), sticky="n"); row_idx+=1
        timer_display_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        timer_display_frame.grid(row=row_idx, column=0, pady=(0,5), padx=10, sticky="ew"); row_idx+=1
        timer_display_frame.grid_columnconfigure(0, weight=1)
        self.focus_break_time_label = ctk.CTkLabel(timer_display_frame, text="00:00", font=self.font_focus_break_timer_value, text_color=COLOR_TEXT_PRIMARY)
        self.focus_break_time_label.pack(pady=(0,0))
        self.focus_break_status_label = ctk.CTkLabel(timer_display_frame, text="FOCUS", font=self.font_focus_break_status, text_color=COLOR_TEXT_SECONDARY)
        self.focus_break_status_label.pack(pady=(0,1))

        settings_info_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        settings_info_frame.grid(row=row_idx, column=0, pady=(0,0), padx=10, sticky="ew"); row_idx+=1
        settings_info_frame.grid_columnconfigure(0, weight=1)
        entry_style = {"font": self.font_settings_entries, "border_width": 1, "corner_radius": 3, "width": 30, "height": 20, "justify": "center", "border_color": "#444"}
        label_style = {"font": self.font_settings_labels, "text_color": COLOR_TEXT_SECONDARY}
        settings_grid = ctk.CTkFrame(settings_info_frame, fg_color="transparent")
        settings_grid.pack(pady=(0,2)) 
        settings_grid.grid_columnconfigure((0,1,2,3,4,5), weight=0)
        ctk.CTkLabel(settings_grid, text="Focus(m):", **label_style).grid(row=0, column=0, padx=(0,1), sticky="e")
        self.focus_minutes_entry = ctk.CTkEntry(settings_grid, **entry_style); self.focus_minutes_entry.insert(0, str(INITIAL_FOCUS_MINUTES)); self.focus_minutes_entry.grid(row=0, column=1, padx=(0,5), sticky="w")
        ctk.CTkLabel(settings_grid, text="Break(m):", **label_style).grid(row=0, column=2, padx=(5,1), sticky="e")
        self.break_minutes_entry = ctk.CTkEntry(settings_grid, **entry_style); self.break_minutes_entry.insert(0, str(INITIAL_BREAK_MINUTES)); self.break_minutes_entry.grid(row=0, column=3, padx=(0,5), sticky="w")
        ctk.CTkLabel(settings_grid, text="Delay(s):", **label_style).grid(row=0, column=4, padx=(5,1), sticky="e")
        self.inactivity_timeout_entry = ctk.CTkEntry(settings_grid, **entry_style); self.inactivity_timeout_entry.insert(0, str(int(_current_inactivity_timeout))); self.inactivity_timeout_entry.grid(row=0, column=5, padx=(0,0), sticky="w")
        
        apply_btn_style = {"font": self.font_buttons, "corner_radius": 4, "height": 20, "text_color": COLOR_BUTTON_TEXT, "border_width": 1, "border_color": "#444", "fg_color": COLOR_BUTTON_FG, "hover_color": COLOR_BUTTON_HOVER, "width": 40}
        buttons_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        buttons_frame.grid(row=row_idx, column=0, pady=(2,5), padx=10, sticky="ew"); row_idx+=1
        buttons_frame.grid_columnconfigure((0,1), weight=1, uniform="apply_btns")
        self.apply_timer_settings_button = ctk.CTkButton(buttons_frame, text="APPLY TIMER", command=self.apply_timer_settings, **apply_btn_style)
        self.apply_timer_settings_button.grid(row=0, column=0, padx=3, sticky="ew")
        self.apply_inactivity_timeout_button = ctk.CTkButton(buttons_frame, text="APPLY DELAY", command=self.apply_inactivity_timeout_setting, **apply_btn_style)
        self.apply_inactivity_timeout_button.grid(row=0, column=1, padx=3, sticky="ew")
        
        ctk.CTkFrame(right_panel, height=1, fg_color="#333").grid(row=row_idx, column=0, pady=(5,5), padx=20, sticky="ew"); row_idx+=1


        self.focus_history_title_label = ctk.CTkLabel(right_panel, text="FOCUS SESSION HISTORY", font=self.font_log_title, text_color=COLOR_TEXT_SECONDARY)
        self.focus_history_title_label.grid(row=row_idx, column=0, pady=(6,1), sticky="n"); row_idx+=1
        self.focus_history_textbox = ctk.CTkTextbox(right_panel, fg_color=FOCUS_HISTORY_BG, text_color=FOCUS_HISTORY_FG, font=self.font_focus_history_text, wrap="word", state="disabled", border_width=1, border_color="#333")
        self.focus_history_textbox.grid(row=row_idx, column=0, sticky="nsew", padx=10, pady=(0,10)); row_idx+=1
        
        self.event_log_title_label = ctk.CTkLabel(right_panel, text="EVENT LOG", font=self.font_log_title, text_color=COLOR_TEXT_SECONDARY)
        self.event_log_title_label.grid(row=row_idx, column=0, pady=(6,1), sticky="n"); row_idx+=1
        self.event_log_console = ctk.CTkTextbox(right_panel, fg_color=CONSOLE_BG, text_color=CONSOLE_FG, font=self.font_event_log_console, wrap="word", state="disabled", border_width=1, border_color="#333")
        self.event_log_console.grid(row=row_idx, column=0, sticky="nsew", padx=10, pady=(0,10)); row_idx+=1

        ctk.CTkFrame(right_panel, height=1, fg_color="#333").grid(row=row_idx, column=0, pady=(5,5), padx=20, sticky="ew"); row_idx+=1
        
        # Time Info Frame at the bottom of the right panel
        time_info_bottom_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        time_info_bottom_frame.grid(row=row_idx, column=0, pady=(5,10), padx=10, sticky="ew")
        time_info_bottom_frame.grid_columnconfigure(0, weight=1) # Center content

        self.total_session_time_label_right = ctk.CTkLabel(time_info_bottom_frame, text="TOTAL SESSION: 00:00:00", 
                                                           font=self.font_total_session_time_right, 
                                                           text_color=COLOR_TEXT_SECONDARY)
        self.total_session_time_label_right.pack(pady=1)

        self.current_time_label_right = ctk.CTkLabel(time_info_bottom_frame, text="00:00:00", 
                                                    font=self.font_clock_right, 
                                                    text_color=COLOR_CLOCK_TEXT)
        self.current_time_label_right.pack(pady=1)


    def on_window_resize_debounced(self, event=None):
        if self._resize_debounce_timer: self.after_cancel(self._resize_debounce_timer)
        self._resize_debounce_timer = self.after(150, lambda e=event: self.on_window_resize(e))

    def on_window_resize(self, event=None):
        if event and hasattr(event, 'widget') and event.widget != self: return
        try:
            if not self.winfo_exists(): return
            current_width = self.winfo_width(); scale = current_width / BASE_WINDOW_WIDTH
            if current_width <= 0: return
            def fs(base, min_s): return max(min_s, int(base * scale))

            self.font_total_session_time_right = (APP_FONT_FAMILY, fs(BASE_FONT_SIZE_TOTAL_SESSION_TIME_RIGHT, MIN_FONT_SIZE_TOTAL_SESSION_TIME_RIGHT), "bold")
            self.font_clock_right = (APP_FONT_FAMILY, fs(BASE_FONT_SIZE_CLOCK_RIGHT, MIN_FONT_SIZE_CLOCK_RIGHT), "bold")
            self.font_prominent_current_stats = (APP_FONT_FAMILY, fs(BASE_FONT_SIZE_PROMINENT_CURRENT_STATS, MIN_FONT_SIZE_PROMINENT_CURRENT_STATS), "bold")
            self.font_prominent_stats_subtitle = (APP_FONT_FAMILY, fs(BASE_FONT_SIZE_PROMINENT_STATS_SUBTITLE, MIN_FONT_SIZE_PROMINENT_STATS_SUBTITLE), "normal")
            self.font_grid_counters=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_GRID_COUNTERS,MIN_FONT_SIZE_GRID_COUNTERS),"bold")
            self.font_grid_subtitles=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_GRID_SUBTITLES,MIN_FONT_SIZE_GRID_SUBTITLES),"normal")
            self.font_focus_break_timer_value=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_FOCUS_BREAK_TIMER,MIN_FONT_SIZE_FOCUS_BREAK_TIMER),"bold")
            self.font_focus_break_status=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_FOCUS_BREAK_STATUS,MIN_FONT_SIZE_FOCUS_BREAK_STATUS),"bold")
            self.font_section_titles=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_SECTION_TITLES,MIN_FONT_SIZE_SECTION_TITLES),"bold")
            self.font_buttons=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_BUTTONS,MIN_FONT_SIZE_BUTTONS),"bold")
            self.font_settings_labels=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_SETTINGS_LABELS,MIN_FONT_SIZE_SETTINGS_LABELS))
            self.font_settings_entries=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_SETTINGS_ENTRIES,MIN_FONT_SIZE_SETTINGS_ENTRIES))
            self.font_effectiveness_value=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_EFFECTIVENESS_VALUE,MIN_FONT_SIZE_EFFECTIVENESS_VALUE),"bold")
            self.font_effectiveness_title=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_EFFECTIVENESS_TITLE,MIN_FONT_SIZE_SECTION_TITLES),"bold")
            self.font_log_title = (APP_FONT_FAMILY, fs(BASE_FONT_SIZE_LOG_TITLE, 10), "bold")
            self.font_focus_history_text = (APP_FONT_FAMILY, fs(BASE_FONT_SIZE_FOCUS_HISTORY_TEXT, MIN_FONT_SIZE_FOCUS_HISTORY_TEXT))
            self.font_event_log_console = (APP_FONT_FAMILY, fs(CONSOLE_FONT_SIZE, 7))

            if hasattr(self,'timed_break_status_label'): self.timed_break_status_label.configure(font=(APP_FONT_FAMILY, fs(BASE_FONT_SIZE_BUTTONS-1, MIN_FONT_SIZE_BUTTONS-1 if MIN_FONT_SIZE_BUTTONS > 7 else 7 ), "bold"))
            # No longer have total_session_time_label at top
            # No longer have current_time_label in the left panel

            if hasattr(self,'effectiveness_title_label'):self.effectiveness_title_label.configure(font=self.font_effectiveness_title)
            if hasattr(self,'effectiveness_value_label'):self.effectiveness_value_label.configure(font=self.font_effectiveness_value)
            if hasattr(self,'current_active_title_label'): self.current_active_title_label.configure(font=self.font_prominent_stats_subtitle)
            if hasattr(self,'current_active_val_label'): self.current_active_val_label.configure(font=self.font_prominent_current_stats)
            if hasattr(self,'current_idle_title_label'): self.current_idle_title_label.configure(font=self.font_prominent_stats_subtitle)
            if hasattr(self,'current_idle_val_label'): self.current_idle_val_label.configure(font=self.font_prominent_current_stats)
            stats_attrs=["total_active_today","max_active_today","prev_active_spell", "total_idle_today","max_idle_today","prev_idle_spell", "mouse_dist","keystrokes", "mouse_clicks"]
            for attr_base in stats_attrs:
                attr_val = f"{attr_base}_grid_val"; attr_title = f"{attr_base}_grid_title"
                if hasattr(self,attr_val)and getattr(self,attr_val).winfo_exists(): getattr(self,attr_val).configure(font=self.font_grid_counters)
                if hasattr(self,attr_title)and getattr(self,attr_title).winfo_exists():getattr(self,attr_title).configure(font=self.font_grid_subtitles)
            if hasattr(self,'focus_break_status_label'):self.focus_break_status_label.configure(font=self.font_focus_break_status)
            if hasattr(self,'focus_break_time_label'):self.focus_break_time_label.configure(font=self.font_focus_break_timer_value)
            
            if hasattr(self,'focus_history_title_label'): self.focus_history_title_label.configure(font=self.font_log_title)
            if hasattr(self,'focus_history_textbox'): self.focus_history_textbox.configure(font=self.font_focus_history_text)
            if hasattr(self,'event_log_title_label'): self.event_log_title_label.configure(font=self.font_log_title)
            if hasattr(self,'event_log_console'): self.event_log_console.configure(font=self.font_event_log_console)

            if hasattr(self, 'total_session_time_label_right'): self.total_session_time_label_right.configure(font=self.font_total_session_time_right)
            if hasattr(self, 'current_time_label_right'): self.current_time_label_right.configure(font=self.font_clock_right)


            btn_s={"font":self.font_buttons}
            buttons_to_scale = ['reset_activity_button', 'pause_session_button', 'continue_session_button',
                                'add_five_min_break_button', 'pause_thirty_min_button', 'pause_one_hour_button',
                                'apply_timer_settings_button','apply_inactivity_timeout_button']
            for btn_n in buttons_to_scale:
                if hasattr(self,btn_n)and getattr(self,btn_n).winfo_exists():getattr(self,btn_n).configure(**btn_s)
            
            entry_s={"font":self.font_settings_entries}
            for entry_n in['focus_minutes_entry','break_minutes_entry','inactivity_timeout_entry']:
                 if hasattr(self,entry_n)and getattr(self,entry_n).winfo_exists():getattr(self,entry_n).configure(**entry_s)
        except Exception as e:print(f"Resize error: {e}\n{traceback.format_exc()}")

    def _update_pause_button_states(self):
        is_manually_paused = self.session_globally_paused and not self.timed_break_active
        is_on_timed_break = self.timed_break_active
        is_running_normally = not self.session_globally_paused and not self.timed_break_active

        if hasattr(self, 'pause_session_button'):
            self.pause_session_button.configure(state="normal" if is_running_normally else "disabled")
        if hasattr(self, 'continue_session_button'):
            self.continue_session_button.configure(state="normal" if is_manually_paused or is_on_timed_break else "disabled")
        if hasattr(self, 'add_five_min_break_button'):
            self.add_five_min_break_button.configure(state="disabled" if is_manually_paused else "normal")
        
        fixed_timed_buttons = [getattr(self, name, None) for name in ['pause_thirty_min_button', 'pause_one_hour_button']]
        for btn in fixed_timed_buttons:
            if btn: btn.configure(state="normal" if is_running_normally else "disabled")
        
        if hasattr(self, 'reset_activity_button'): self.reset_activity_button.configure(state="normal")
    
    def manual_pause_session(self):
        if self.timed_break_active or self.session_globally_paused: return
        self.session_globally_paused = True
        self.session_pause_start_time = time.time()
        add_log_message(self, "Session Paused Manually.")
        self._update_pause_button_states()

    def manual_continue_session(self):
        if self.timed_break_active:
            add_log_message(self, f"Timed break of {self.timed_break_duration_seconds//60}m interrupted by Continue.")
            self.end_timed_break() 
        elif self.session_globally_paused and not self.timed_break_active: 
            if self.session_pause_start_time:
                self.total_session_time_actively_paused += (time.time() - self.session_pause_start_time)
            self.session_globally_paused = False
            self.session_pause_start_time = None
            add_log_message(self, "Session Continued Manually.")
            self._update_pause_button_states()

    def add_or_start_5_min_break(self):
        if self.session_globally_paused and not self.timed_break_active:
            add_log_message(self, "Cannot add/start 5min break while session is manually paused.")
            return

        five_minutes = 5 * 60
        if self.timed_break_active:
            if self.timed_break_end_time: 
                self.timed_break_end_time += five_minutes
                self.timed_break_duration_seconds += five_minutes 
                remaining = self.timed_break_end_time - time.time()
                add_log_message(self, f"+5min added to break. New total: {self.timed_break_duration_seconds//60}m. Remaining: {format_ms_string(remaining)}")
            else:
                add_log_message(self, "Error: Tried to extend break with no end time. Starting new 5min break.")
                self.start_timed_break(five_minutes, is_extendable=True) 
        else:
            self.start_timed_break(five_minutes, is_extendable=True)
        
        self._update_pause_button_states() 
        self.update_gui_display()      

    def start_timed_break(self, duration_seconds: int, is_extendable: bool = False):
        if self.session_globally_paused and not self.timed_break_active:
             add_log_message(self, "Cannot start timed break while session is manually paused.")
             return
        if self.timed_break_active and not is_extendable:
            add_log_message(self, "Another timed break is already active. Cannot start a new fixed break.")
            return
        
        self.timed_break_active = True
        self.timed_break_duration_seconds = duration_seconds 
        self.timed_break_end_time = time.time() + duration_seconds
        
        if not self.session_globally_paused:
            self.session_globally_paused = True
            self.session_pause_start_time = time.time()
            self.timed_break_initiated_pause = True
        else: 
            self.timed_break_initiated_pause = False
            
        add_log_message(self, f"Timed break for {duration_seconds//60} minutes started.")
        self._update_pause_button_states()
        self.update_gui_display()

    def end_timed_break(self):
        if not self.timed_break_active: return
        
        break_duration_minutes = self.timed_break_duration_seconds // 60
        
        if self.timed_break_initiated_pause and self.session_pause_start_time:
             self.total_session_time_actively_paused += (time.time() - self.session_pause_start_time)
        
        self.timed_break_active = False
        self.timed_break_duration_seconds = 0
        self.timed_break_end_time = None
        
        if self.timed_break_initiated_pause: 
            self.session_globally_paused = False
            self.session_pause_start_time = None 
        
        self.timed_break_initiated_pause = False
        
        self.timed_break_status_label.configure(text="")
        add_log_message(self, f"Timed break ({break_duration_minutes}m) finished.")
        self._update_pause_button_states()
        self.update_gui_display()


    def reset_daily_activity_counter(self):
        now=time.time()
        with state_lock:
            app_state.update({
                "total_active_seconds_today":0.0,"total_idle_seconds_today":0.0,
                "max_idle_seconds_today":0.0,"max_active_seconds_today":0.0,
                "mouse_total_distance_today":0.0,"keystrokes_today":0,"mouse_clicks_today":0,
                "last_activity_duration":0.0, "last_inactivity_duration":0.0,
                "current_idle_start_time":None,"current_activity_start_time":now,
                "last_activity_time":now,"prev_overall_active_state":True,"mouse_last_pos_for_distance":None
            })
        add_log_message(self,"Daily stats reset.")

    def update_gui_display(self):
        if not self.winfo_exists():return
        now=time.time();now_dt=datetime.datetime.now()

        # Total Session Time (now displayed on the right)
        if self.session_globally_paused and self.session_pause_start_time:
            effective_running_time = (self.session_pause_start_time - self.app_launch_time) - self.total_session_time_actively_paused
        else:
            effective_running_time = (now - self.app_launch_time) - self.total_session_time_actively_paused
        if hasattr(self, 'total_session_time_label_right'): # Updated attribute name
             self.total_session_time_label_right.configure(text=f"{format_hms_string(effective_running_time)}")

        # Current Time (now displayed on the right)
        if hasattr(self,'current_time_label_right'): # Updated attribute name
            self.current_time_label_right.configure(text=now_dt.strftime('%H:%M:%S'))


        if self.timed_break_active and self.timed_break_end_time:
            remaining_break = self.timed_break_end_time - time.time() 
            base_font_size = BASE_FONT_SIZE_TOTAL_SESSION_TIME_RIGHT * 1.2 # Example for slightly larger status
            if remaining_break > 0: 
                self.timed_break_status_label.configure(
                    text=f"ON {self.timed_break_duration_seconds//60} MIN BREAK - {format_hms_string(remaining_break)} left",
                    font=(APP_FONT_FAMILY, int(base_font_size), "bold")
                )
            else: 
                self.timed_break_status_label.configure(
                    text=f"{self.timed_break_duration_seconds//60} MIN BREAK ENDING...",
                    font=(APP_FONT_FAMILY, int(base_font_size), "bold")
                )
        elif hasattr(self, 'timed_break_status_label'): self.timed_break_status_label.configure(text="")

        with state_lock:s=app_state.copy()
        is_manually_paused = self.session_globally_paused and not self.timed_break_active

        if is_manually_paused:
            if hasattr(self,'current_active_val_label'): self.current_active_val_label.configure(text="PAUSED")
            if hasattr(self,'current_idle_val_label'): self.current_idle_val_label.configure(text="PAUSED")
            if hasattr(self,'focus_break_time_label'): self.focus_break_time_label.configure(text="PAUSED")
            if hasattr(self,'focus_break_status_label'): self.focus_break_status_label.configure(text="SESSION PAUSED")
        elif self.timed_break_active: 
            if hasattr(self,'focus_break_time_label'): self.focus_break_time_label.configure(text="ON BREAK", font=(APP_FONT_FAMILY, int(BASE_FONT_SIZE_FOCUS_BREAK_TIMER * 1.2), "bold"))
            if hasattr(self,'focus_break_status_label'): self.focus_break_status_label.configure(text=f"{self.timed_break_duration_seconds//60} MIN BREAK")
            active_now=(now-s["last_activity_time"])< _current_inactivity_timeout
            current_idle_s=0.0; current_active_s=0.0
            if active_now:
                if s["current_activity_start_time"]:current_active_s=now-s["current_activity_start_time"]
            else:
                if s["current_idle_start_time"]:current_idle_s=now-s["current_idle_start_time"]
            if hasattr(self,'current_active_val_label'):self.current_active_val_label.configure(text=format_hms_string(current_active_s))
            if hasattr(self,'current_idle_val_label'):self.current_idle_val_label.configure(text=format_hms_string(current_idle_s))
        else: # Running normally
            active_now=(now-s["last_activity_time"])< _current_inactivity_timeout
            current_idle_s=0.0; current_active_s=0.0
            if active_now:
                if s["current_activity_start_time"]:current_active_s=now-s["current_activity_start_time"]
            else:
                if s["current_idle_start_time"]:current_idle_s=now-s["current_idle_start_time"]
            if hasattr(self,'current_active_val_label'):self.current_active_val_label.configure(text=format_hms_string(current_active_s))
            if hasattr(self,'current_active_title_label'):self.current_active_title_label.configure(text_color=COLOR_ACCENT_ACTIVE_MOUSE if active_now and current_active_s > 0.1 else COLOR_TEXT_SECONDARY)
            if hasattr(self,'current_idle_val_label'):self.current_idle_val_label.configure(text=format_hms_string(current_idle_s))
            if hasattr(self,'current_idle_title_label'):self.current_idle_title_label.configure(text_color=COLOR_TEXT_INACTIVE if not active_now and current_idle_s > 0.1 else COLOR_TEXT_SECONDARY)
            timer_mode = s["timer_mode"]; timer_rem = s["timer_seconds_remaining"]
            timer_status_text = timer_mode.upper(); timer_status_color = COLOR_TIMER_FOCUS if timer_mode == "focus" else COLOR_TIMER_BREAK
            if hasattr(self,'focus_break_status_label'):self.focus_break_status_label.configure(text=timer_status_text,text_color=timer_status_color)
            if hasattr(self,'focus_break_time_label'):self.focus_break_time_label.configure(text=format_ms_string(timer_rem))

        eff_p=(s["total_active_seconds_today"]/(s["total_active_seconds_today"]+s["total_idle_seconds_today"])*100)if(s["total_active_seconds_today"]+s["total_idle_seconds_today"])>0 else 0
        eff_c=COLOR_ACCENT_ACTIVE_MOUSE if eff_p >= 66.6 else COLOR_TEXT_INACTIVE
        if hasattr(self,'effectiveness_value_label'):self.effectiveness_value_label.configure(text=f"{eff_p:.1f}%",text_color=eff_c)
        if hasattr(self,'effectiveness_bar')and self.effectiveness_bar_bg.winfo_exists():
            bar_w=self.effectiveness_bar_bg.winfo_width()-4
            if bar_w>0:self.effectiveness_bar.place_configure(width=max(0, min(bar_w, bar_w*(eff_p/100.0))))
            current_bar_color = COLOR_ACCENT_ACTIVE_MOUSE if eff_p >= 66.6 else EFFECTIVENESS_BAR_LOW_COLOR
            self.effectiveness_bar.configure(fg_color=current_bar_color)

        if hasattr(self,'total_active_today_grid_val'):self.total_active_today_grid_val.configure(text=format_hms_string(s["total_active_seconds_today"]))
        # ... (other grid stats updates)
        if hasattr(self,'max_active_today_grid_val'):self.max_active_today_grid_val.configure(text=format_hms_string(s["max_active_seconds_today"]))
        if hasattr(self,'prev_active_spell_grid_val'):self.prev_active_spell_grid_val.configure(text=format_hms_string(s["last_activity_duration"])if s["last_activity_duration"]>0.1 else"N/A")
        if hasattr(self,'prev_idle_spell_grid_val'):self.prev_idle_spell_grid_val.configure(text=format_hms_string(s["last_inactivity_duration"])if s["last_inactivity_duration"]>0.1 else"N/A")
        if hasattr(self,'mouse_dist_grid_val'):self.mouse_dist_grid_val.configure(text=f"{s['mouse_total_distance_today']:,.0f}")
        if hasattr(self,'keystrokes_grid_val'):self.keystrokes_grid_val.configure(text=f"{s['keystrokes_today']:,}")
        if hasattr(self,'total_idle_today_grid_val'):self.total_idle_today_grid_val.configure(text=format_hms_string(s["total_idle_seconds_today"]))
        if hasattr(self,'max_idle_today_grid_val'):self.max_idle_today_grid_val.configure(text=format_hms_string(s["max_idle_seconds_today"]))
        if hasattr(self,'mouse_clicks_grid_val'):self.mouse_clicks_grid_val.configure(text=f"{s.get('mouse_clicks_today', 0):,}")
        
        if hasattr(self, 'focus_history_textbox') and self.focus_history_textbox.winfo_exists():
            self.focus_history_textbox.configure(state="normal")
            self.focus_history_textbox.delete("1.0", "end")
            if not self._color_tags_defined:
                self.focus_history_textbox.tag_config("eff_good", foreground=COLOR_ACCENT_ACTIVE_MOUSE)
                self.focus_history_textbox.tag_config("eff_bad", foreground=COLOR_TEXT_INACTIVE)
                self._color_tags_defined = True

            for entry in list(s["focus_session_log"]):
                eff = entry['effectiveness']
                tag_to_use = "eff_good" if eff >= 66.6 else "eff_bad"
                log_text = f"Focus ({entry['duration_minutes']}m) at {entry['end_time_str']} - {eff:.1f}% effective\n"
                self.focus_history_textbox.insert("end", log_text, (tag_to_use,))
            self.focus_history_textbox.configure(state="disabled")
        
        if app_state["running"]:self.after(int(ACTIVITY_CHECK_INTERVAL*1000),self.update_gui_display)

    def apply_timer_settings(self):
        try:
            f_m,b_m=int(self.focus_minutes_entry.get()),int(self.break_minutes_entry.get())
            if not(0<f_m<1000 and 0<b_m<1000):raise ValueError("Durations out of range.")
            with state_lock:
                app_state.update({"focus_duration_seconds":f_m*60,"break_duration_seconds":b_m*60})
                app_state["timer_mode"] = "focus"
                app_state["timer_seconds_remaining"] = app_state["focus_duration_seconds"]
                app_state["current_focus_active_seconds"] = 0.0
            add_log_message(self,f"Timer Settings: Focus {f_m}m, Break {b_m}m. Timer reset to Focus.")
        except Exception as e:add_log_message(self,f"Timer settings error: {e}")

    def apply_inactivity_timeout_setting(self):
        global _current_inactivity_timeout
        try:
            new_timeout=float(self.inactivity_timeout_entry.get())
            if not(1.0<=new_timeout<=3600.0):raise ValueError("Timeout 1-3600s.")
            _current_inactivity_timeout=new_timeout
            add_log_message(self,f"Inactivity timeout: {_current_inactivity_timeout:.1f}s.")
        except Exception as e:
            add_log_message(self,f"Timeout error: {e}")
            self.inactivity_timeout_entry.delete(0,"end");self.inactivity_timeout_entry.insert(0,str(int(_current_inactivity_timeout)))

    def tracking_loop(self):
        global _current_inactivity_timeout
        last_save = time.time(); last_inactivity_log = 0; active_now_local = False
        while True:
            with state_lock: running = app_state["running"]
            if not running: break
            now = time.time()
            if self.timed_break_active and self.timed_break_end_time and now >= self.timed_break_end_time:
                self.after(0, self.end_timed_break)
            if self.session_globally_paused: 
                time.sleep(ACTIVITY_CHECK_INTERVAL); continue
            today_iso = datetime.date.today().isoformat()
            with state_lock: current_day_s = app_state["current_day_string"]
            if current_day_s != today_iso:
                add_log_message(self, f"Day change: {today_iso}. Resetting counters.")
                save_daily_data()
                with state_lock:
                    app_state.update({
                        "current_day_string": today_iso, "total_active_seconds_today": 0.0, "total_idle_seconds_today": 0.0,
                        "max_idle_seconds_today": 0.0, "max_active_seconds_today": 0.0, "mouse_total_distance_today": 0.0, 
                        "keystrokes_today": 0, "mouse_clicks_today": 0, "last_activity_duration": 0.0, 
                        "last_inactivity_duration": 0.0, "current_idle_start_time": None, "current_activity_start_time": now,
                        "last_activity_time": now, "prev_overall_active_state": True, "mouse_last_pos_for_distance": None,
                        "current_focus_active_seconds": 0.0,
                    })
                load_daily_data()
            with state_lock:
                s_trk = app_state.copy(); last_act_time = s_trk["last_activity_time"]
                was_active = s_trk["prev_overall_active_state"]; cur_idle_start_ts = s_trk["current_idle_start_time"]
                cur_act_start_ts = s_trk["current_activity_start_time"]; cur_max_idle = s_trk["max_idle_seconds_today"]
                cur_max_active = s_trk["max_active_seconds_today"]
            active_now_local = (now - last_act_time) < _current_inactivity_timeout
            updates = {}; log_msg_parts = []
            if was_active and not active_now_local:
                updates["current_idle_start_time"] = last_act_time
                if cur_act_start_ts is not None:
                    act_dur = last_act_time - cur_act_start_ts
                    if act_dur > 0: updates["last_activity_duration"] = act_dur; updates["max_active_seconds_today"] = max(cur_max_active, act_dur)
                updates["current_activity_start_time"] = None; log_msg_parts.append("Became inactive.")
            elif not was_active and active_now_local:
                updates["current_activity_start_time"] = now
                if cur_idle_start_ts is not None:
                    idle_dur = now - cur_idle_start_ts
                    if idle_dur > 1.0: updates["last_inactivity_duration"] = idle_dur; updates["max_idle_seconds_today"] = max(cur_max_idle, idle_dur); log_msg_parts.append(f"Active after {format_hms_string(idle_dur)} idle.")
                    else: log_msg_parts.append("Active (short idle).")
                else: log_msg_parts.append("Became active.")
                updates["current_idle_start_time"] = None
            with state_lock:
                app_state.update(updates)
                if active_now_local: app_state["total_active_seconds_today"] += ACTIVITY_CHECK_INTERVAL
                elif app_state["current_idle_start_time"] is not None: app_state["total_idle_seconds_today"] += ACTIVITY_CHECK_INTERVAL
                app_state["prev_overall_active_state"] = active_now_local
            current_inactive_seconds_for_log = 0 if active_now_local else (now - app_state.get("current_idle_start_time", now))
            if not active_now_local and current_inactive_seconds_for_log >= LONG_INACTIVITY_THRESHOLD and (now - last_inactivity_log >= LONG_INACTIVITY_THRESHOLD):
                log_msg_parts.append(f"Still inactive ({round(current_inactive_seconds_for_log / 60)}m)")
                last_inactivity_log = now
            elif active_now_local: last_inactivity_log = 0
            with state_lock:
                timer_mode = app_state["timer_mode"]; focus_duration_for_log = app_state["focus_duration_seconds"]
                if timer_mode == "focus" and active_now_local: app_state["current_focus_active_seconds"] += ACTIVITY_CHECK_INTERVAL
                current_timer_remaining = app_state["timer_seconds_remaining"] - ACTIVITY_CHECK_INTERVAL
                app_state["timer_seconds_remaining"] = current_timer_remaining
                if current_timer_remaining <= 0:
                    break_duration = app_state["break_duration_seconds"]
                    if timer_mode == "focus":
                        active_in_focus = app_state["current_focus_active_seconds"]; effectiveness = 0.0
                        if focus_duration_for_log > 0: effectiveness = (active_in_focus / focus_duration_for_log) * 100
                        
                        timestamp_str = datetime.datetime.now().strftime('%H:%M:%S')
                        log_focus_session(effectiveness, int(focus_duration_for_log / 60), timestamp_str)
                        
                        log_entry = {'effectiveness': effectiveness, 'end_time_str': timestamp_str, 'duration_minutes': int(focus_duration_for_log / 60)}
                        app_state["focus_session_log"].appendleft(log_entry)
                        
                        log_msg_parts.append(f"Focus ({log_entry['duration_minutes']}m) ended. Eff: {effectiveness:.1f}%.")
                        app_state["timer_mode"] = "break"; app_state["timer_seconds_remaining"] = break_duration
                        app_state["current_focus_active_seconds"] = 0.0
                        log_msg_parts.append(f"Starting Break ({int(break_duration/60)}m).")
                    elif timer_mode == "break":
                        focus_duration_next = app_state["focus_duration_seconds"]
                        app_state["timer_mode"] = "focus"; app_state["timer_seconds_remaining"] = focus_duration_next
                        app_state["current_focus_active_seconds"] = 0.0
                        log_msg_parts.append(f"Break ({int(break_duration/60)}m) ended. Starting Focus ({int(focus_duration_next/60)}m).")
            if log_msg_parts:
                final_log_msg = " ".join(log_msg_parts)
                self.after(0, lambda msg=final_log_msg: add_log_message(self, msg))
            if now - last_save > 60: save_daily_data(); last_save = now
            time.sleep(max(0, ACTIVITY_CHECK_INTERVAL - (time.time() - now)))
        print("Tracking loop finished.")

    def start_mouse_listener(self):
        try: threading.Thread(target=pynput.mouse.Listener(on_move=on_move, on_click=on_click).start, daemon=True, name="MouseListener").start()
        except Exception as e: add_log_message(self,f"Mouse listener error: {e}")
    def start_keyboard_listener(self):
        try: threading.Thread(target=pynput.keyboard.Listener(on_press=on_key_press).start,daemon=True,name="KeyboardListener").start()
        except Exception as e: add_log_message(self,f"Keyboard listener error: {e}")
    def start_tracking_loop(self):
        try: self.tracking_thread=threading.Thread(target=self.tracking_loop,daemon=True,name="TrackingLoop");self.tracking_thread.start()
        except Exception as e: add_log_message(self,f"Tracking loop error: {e}")
    def on_closing(self):
        add_log_message(self,"Shutdown initiated...")
        with state_lock:app_state["running"]=False
        if hasattr(self,'tracking_thread')and self.tracking_thread.is_alive():
            add_log_message(self,"Waiting for tracking loop...");self.tracking_thread.join(timeout=0.5)
        add_log_message(self,"Final save...");save_daily_data();add_log_message(self,"Exiting.");print("App closed.")
        self.destroy()

def log_focus_session(effectiveness: float, duration_minutes: int, timestamp: str):
    try:
        with open("focus_session_log.txt", "a", encoding="utf-8") as f:
            status = "EFFECTIVE" if effectiveness >= 66.6 else "NEEDS IMPROVEMENT"
            f.write(f"[{timestamp}] {duration_minutes}min Focus Session - {effectiveness:.1f}% ({status})\n")
    except Exception as e:
        print(f"Error writing to focus log: {e}")

if __name__=="__main__":
    try:
        if hasattr(sys,'_MEIPASS'):os.chdir(sys._MEIPASS)
        elif"__file__"in locals()or"__file__"in globals():os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except Exception as e:print(f"CWD Error: {e}")
    app=DominantBorderHubApp()
    app.mainloop()
