import customtkinter as ctk
import time
import datetime
import json
import os
import threading
import pynput.mouse
import pynput.keyboard
from typing import Optional
import traceback
import sys
import math

# --- Configuration ---
APP_NAME = "activitytracker3000"
DATA_FILE = "mouse_activity_log.json"
ACTIVITY_CHECK_INTERVAL = 0.1
INITIAL_INACTIVITY_TIMEOUT = 10.0
LONG_INACTIVITY_THRESHOLD = 600.0
INITIAL_WORK_MINUTES = 25
INITIAL_SHORT_BREAK_MINUTES = 5

APP_FONT_FAMILY = "helvetica"
BASE_WINDOW_WIDTH = 850 
BASE_WINDOW_HEIGHT = 400
# Font sizes
BASE_FONT_SIZE_CLOCK = 50
BASE_FONT_SIZE_PROMINENT_CURRENT_STATS = 60 # For Current Active/Idle
BASE_FONT_SIZE_PROMINENT_STATS_SUBTITLE = 16

BASE_FONT_SIZE_GRID_COUNTERS = 24 # For the smaller stats grid
BASE_FONT_SIZE_GRID_SUBTITLES = 12 

BASE_FONT_SIZE_POMO_TIMER = 30 
BASE_FONT_SIZE_POMO_STATUS = 13 
BASE_FONT_SIZE_SECTION_TITLES = 14 # For "POMODORO", "SETTINGS & INFO"
BASE_FONT_SIZE_BUTTONS = 10
BASE_FONT_SIZE_SETTINGS_LABELS = 9 
BASE_FONT_SIZE_SETTINGS_ENTRIES = 10
BASE_FONT_SIZE_LOG_TITLE = 13

MIN_FONT_SIZE_CLOCK = 14
MIN_FONT_SIZE_PROMINENT_CURRENT_STATS = 24
MIN_FONT_SIZE_PROMINENT_STATS_SUBTITLE = 10
MIN_FONT_SIZE_GRID_COUNTERS = 9
MIN_FONT_SIZE_GRID_SUBTITLES = 6
MIN_FONT_SIZE_POMO_TIMER = 14
MIN_FONT_SIZE_POMO_STATUS = 6
MIN_FONT_SIZE_SECTION_TITLES = 9
MIN_FONT_SIZE_BUTTONS = 8
MIN_FONT_SIZE_SETTINGS_LABELS = 14
MIN_FONT_SIZE_SETTINGS_ENTRIES = 14


BASE_FONT_SIZE_EFFECTIVENESS_VALUE = 48 # For top effectiveness display
MIN_FONT_SIZE_EFFECTIVENESS_VALUE = 18
BASE_FONT_SIZE_EFFECTIVENESS_TITLE = BASE_FONT_SIZE_SECTION_TITLES


COLOR_WINDOW_BG="#2a2a2a"; COLOR_MAIN_CONTENT_BG="#1D1D1D"; COLOR_BORDER="#1D1D1D"
BORDER_THICKNESS=15; COLOR_TEXT_PRIMARY="#F0F0F0"; COLOR_TEXT_SECONDARY="#A9A9A9"
COLOR_TEXT_INACTIVE="#FF3B30"; COLOR_CLOCK_TEXT="#E8D85C"; COLOR_ACCENT_ACTIVE_MOUSE="#30D158"
COLOR_POMO_TIMER_RUNNING="#28C740"; COLOR_BUTTON_FG="#2E2E2E"; COLOR_BUTTON_HOVER="#3F3F3F"
COLOR_BUTTON_TEXT=COLOR_TEXT_PRIMARY; CONSOLE_BG="#1a1a1a"; CONSOLE_FG="#a0a0a0"
CONSOLE_FONT_SIZE=9; MAX_LOG_LINES=1000; EFFECTIVENESS_BAR_HEIGHT=6
EFFECTIVENESS_BAR_LOW_COLOR="#404040"
# --- End Configuration ---

_current_inactivity_timeout = INITIAL_INACTIVITY_TIMEOUT

app_state = { # State variables remain comprehensive
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
    "pomodoro_work_duration_seconds": INITIAL_WORK_MINUTES*60,
    "pomodoro_break_duration_seconds": INITIAL_SHORT_BREAK_MINUTES*60,
    "pomodoro_mode": "idle", "pomodoro_seconds_remaining": INITIAL_WORK_MINUTES*60,
    "pomodoro_start_time": 0, "pomodoro_paused_seconds_remaining": 0,
    "last_reset_time": None,
    "mouse_clicks_today": 0,
}
state_lock = threading.Lock()

def format_hms_string(s):
    s=max(0,s); h=s//3600; m=(s%3600)//60; s%=60; return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
def format_ms_string(s):
    s=max(0,s); m=s//60; s%=60; return f"{int(m):02d}:{int(s):02d}"

def on_move(x,y):
    global app_state
    with state_lock:
        now=time.time();pos=(x,y)
        if app_state["mouse_last_pos_for_distance"] is not None:
            px,py=app_state["mouse_last_pos_for_distance"];app_state["mouse_total_distance_today"]+=math.sqrt((x-px)**2+(y-py)**2)
        app_state["mouse_last_pos_for_distance"]=pos
        app_state.update({"last_mouse_position":pos,"last_movement_time":now,"last_activity_time":now})
def on_key_press(key):
    global app_state
    with state_lock:app_state["keystrokes_today"]+=1;app_state.update({"last_keyboard_activity_time":time.time(),"last_activity_time":time.time()})

def on_click(x, y, button, pressed):
    if pressed:  # Only count press events, not releases
        global app_state
        with state_lock:
            app_state["mouse_clicks_today"] += 1
            app_state.update({"last_activity_time": time.time()})

def load_daily_data(): # No change from previous, loads all necessary data
    global app_state
    today_str = datetime.date.today().isoformat()
    default_data = {"active_seconds":0.0, "idle_seconds":0.0, "max_idle_seconds":0.0, 
                    "max_active_seconds":0.0, "mouse_total_distance":0.0, "keystrokes":0,
                    "last_activity_duration":0.0, "last_inactivity_duration":0.0}
    data_today = default_data.copy(); full_data = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE,'r')as f: content=f.read()
            if content:full_data=json.loads(content)
        except Exception as e: print(f"Warning loading {DATA_FILE}: {e}")
    raw_today = full_data.get(today_str)
    if isinstance(raw_today, dict):
        for key in data_today: data_today[key] = float(raw_today.get(key,0.0)) if key not in ["keystrokes"] else int(raw_today.get(key,0))
    elif isinstance(raw_today,(float,int)): data_today["active_seconds"]=float(raw_today)
    with state_lock:
        app_state.update({
            "current_day_string":today_str,
            "total_active_seconds_today":data_today["active_seconds"],"total_idle_seconds_today":data_today["idle_seconds"],
            "max_idle_seconds_today":data_today["max_idle_seconds"],"max_active_seconds_today":data_today["max_active_seconds"],
            "mouse_total_distance_today":data_today["mouse_total_distance"],"keystrokes_today":data_today["keystrokes"],
            "last_activity_duration": data_today["last_activity_duration"],"last_inactivity_duration": data_today["last_inactivity_duration"],
            "current_activity_start_time":time.time(),"current_idle_start_time": None,
        })
def save_daily_data(): # No change from previous
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
            "max_active_seconds_today","mouse_total_distance_today","keystrokes_today",
            "last_activity_duration","last_inactivity_duration"]}
    full_data[day_s]=data_to_save
    try:
        with open(DATA_FILE,'w')as f:json.dump(full_data,f,indent=4)
    except Exception as e:print(f"Error writing to {DATA_FILE}: {e}")
def add_log_message(app_instance,message): # No change
    if not isinstance(app_instance,ctk.CTk)or not hasattr(app_instance,'log_console')or not app_instance.log_console.winfo_exists():print(f"Log Console not ready: {message}");return
    log_text=f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}\n"
    def _update():
        try:
            if not app_instance.log_console.winfo_exists():return
            app_instance.log_console.configure(state="normal")
            lines=[l for l in app_instance.log_console.get("1.0","end-1c").split('\n')if l]
            if len(lines)>=MAX_LOG_LINES:lines=lines[-(MAX_LOG_LINES-1):]
            app_instance.log_console.delete("1.0","end");app_instance.log_console.insert("1.0",'\n'.join(lines+[log_text.strip()])+'\n')
            app_instance.log_console.see("end");app_instance.log_console.configure(state="disabled")
        except Exception as e:print(f"Error GUI log: {e}")
    if app_instance.winfo_exists():app_instance.after(0,_update)

class DominantBorderHubApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME); self.geometry(f"{BASE_WINDOW_WIDTH}x{BASE_WINDOW_HEIGHT}")
        self.minsize(680, 800); ctk.set_appearance_mode("Dark")
        self.configure(fg_color=COLOR_WINDOW_BG); self.app_start_time_dt=datetime.datetime.now()
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
            else:
                print("Icon file not found:", icon_path)
        except Exception as e:
            print(f"Icon error: {e}")

        load_daily_data(); self._init_fonts()

        self.main_split=ctk.CTkFrame(self,fg_color="transparent")
        self.main_split.pack(fill="both",expand=True,padx=15,pady=15)
        self.main_split.grid_columnconfigure(0,weight=3);self.main_split.grid_columnconfigure(1,weight=2)
        self.main_split.grid_rowconfigure(0,weight=1)

        self.main_content_frame=ctk.CTkFrame(self.main_split,fg_color=COLOR_MAIN_CONTENT_BG,border_color=COLOR_BORDER,border_width=BORDER_THICKNESS,corner_radius=0)
        self.main_content_frame.grid(row=0,column=0,sticky="nsew",padx=(0,7))
        self.main_content_frame.grid_columnconfigure(0,weight=1)

        # Define row weights for main_content_frame sections - reduced spacing
        self.main_content_frame.grid_rowconfigure(0, weight=0, minsize=35)  # Clock
        self.main_content_frame.grid_rowconfigure(1, weight=1, minsize=70) # Effectiveness Hub (smaller)
        self.main_content_frame.grid_rowconfigure(2, weight=2, minsize=120) # Prominent Current Active/Idle Stats
        self.main_content_frame.grid_rowconfigure(3, weight=3, minsize=160) # Compact Stats Grid (2x4)
        self.main_content_frame.grid_rowconfigure(4, weight=2, minsize=140) # NEW Pomo & Settings Panel 
        
        self._create_clock_section(); self._create_effectiveness_section()
        self._create_prominent_current_stats_section() # New
        self._create_compact_stats_grid_section() # New
        self._create_pomodoro_settings_info_panel() # Redesigned
        self._create_log_console_section()

        add_log_message(self,"App starting...");self.bind("<Configure>",self.on_window_resize_debounced)
        self._resize_debounce_timer=None
        self.start_mouse_listener();self.start_keyboard_listener();self.start_tracking_loop()
        self.protocol("WM_DELETE_WINDOW",self.on_closing)
        self.update_gui_display();self.after(250,self.on_window_resize)
        add_log_message(self,"App started.")

    def _init_fonts(self):
        self.font_clock=(APP_FONT_FAMILY,BASE_FONT_SIZE_CLOCK,"bold")
        self.font_prominent_current_stats = (APP_FONT_FAMILY, BASE_FONT_SIZE_PROMINENT_CURRENT_STATS, "bold")
        self.font_prominent_stats_subtitle = (APP_FONT_FAMILY, BASE_FONT_SIZE_PROMINENT_STATS_SUBTITLE, "normal")
        self.font_grid_counters=(APP_FONT_FAMILY,BASE_FONT_SIZE_GRID_COUNTERS,"bold")
        self.font_grid_subtitles=(APP_FONT_FAMILY,BASE_FONT_SIZE_GRID_SUBTITLES,"normal")
        self.font_pomo_timer_value=(APP_FONT_FAMILY,BASE_FONT_SIZE_POMO_TIMER,"bold")
        self.font_pomo_status=(APP_FONT_FAMILY,BASE_FONT_SIZE_POMO_STATUS,"bold")
        self.font_section_titles=(APP_FONT_FAMILY,BASE_FONT_SIZE_SECTION_TITLES,"bold")
        self.font_buttons=(APP_FONT_FAMILY,BASE_FONT_SIZE_BUTTONS,"bold")
        self.font_settings_labels=(APP_FONT_FAMILY,BASE_FONT_SIZE_SETTINGS_LABELS,"normal")
        self.font_settings_entries=(APP_FONT_FAMILY,BASE_FONT_SIZE_SETTINGS_ENTRIES,"normal")
        self.font_effectiveness_value=(APP_FONT_FAMILY,BASE_FONT_SIZE_EFFECTIVENESS_VALUE,"bold")
        self.font_effectiveness_title=(APP_FONT_FAMILY,BASE_FONT_SIZE_EFFECTIVENESS_TITLE,"bold")

    def _create_clock_section(self):
        frame=ctk.CTkFrame(self.main_content_frame,fg_color="transparent")
        frame.grid(row=0,column=0,pady=(6,1),padx=15,sticky="nsew")
        self.current_time_label=ctk.CTkLabel(frame,text="00:00:00",font=self.font_clock,text_color=COLOR_CLOCK_TEXT); self.current_time_label.pack(pady=1)
    def _create_effectiveness_section(self):
        frame=ctk.CTkFrame(self.main_content_frame,fg_color="transparent")
        frame.grid(row=1,column=0,pady=1,padx=15,sticky="nsew")
        self.effectiveness_title_label=ctk.CTkLabel(frame,text="SESSION EFFECTIVENESS",font=self.font_effectiveness_title,text_color=COLOR_TEXT_SECONDARY); self.effectiveness_title_label.pack(pady=(0,1))
        self.effectiveness_value_label=ctk.CTkLabel(frame,text="N/A",font=self.font_effectiveness_value,text_color=COLOR_TEXT_PRIMARY); self.effectiveness_value_label.pack(pady=(0,1))
        self.effectiveness_bar_bg=ctk.CTkFrame(frame,fg_color="#404040",height=EFFECTIVENESS_BAR_HEIGHT+4,corner_radius=EFFECTIVENESS_BAR_HEIGHT//2); self.effectiveness_bar_bg.pack(fill="x",padx=30,pady=(0,1))
        self.effectiveness_bar=ctk.CTkFrame(self.effectiveness_bar_bg,fg_color=EFFECTIVENESS_BAR_LOW_COLOR,height=EFFECTIVENESS_BAR_HEIGHT,width=0,corner_radius=(EFFECTIVENESS_BAR_HEIGHT//2)-1); self.effectiveness_bar.place(x=2,y=2,relwidth=0)

    def _create_prominent_current_stats_section(self):
        frame = ctk.CTkFrame(self.main_content_frame, fg_color="transparent")
        frame.grid(row=2, column=0, pady=(5,2), padx=15, sticky="nsew")
        frame.grid_columnconfigure((0,1), weight=1) # Two columns for Current Active and Current Idle

        # Current Active
        active_frame = ctk.CTkFrame(frame, fg_color="transparent")
        active_frame.grid(row=0, column=0, padx=5, pady=2, sticky="nsew")
        self.current_active_title_label = ctk.CTkLabel(active_frame, text="CURRENT ACTIVE", font=self.font_prominent_stats_subtitle, text_color=COLOR_TEXT_SECONDARY)
        self.current_active_title_label.pack(pady=(0,1))
        self.current_active_val_label = ctk.CTkLabel(active_frame, text="00:00:00", font=self.font_prominent_current_stats, text_color=COLOR_TEXT_PRIMARY)
        self.current_active_val_label.pack()

        # Current Idle
        idle_frame = ctk.CTkFrame(frame, fg_color="transparent")
        idle_frame.grid(row=0, column=1, padx=5, pady=2, sticky="nsew")
        self.current_idle_title_label = ctk.CTkLabel(idle_frame, text="CURRENT IDLE", font=self.font_prominent_stats_subtitle, text_color=COLOR_TEXT_SECONDARY)
        self.current_idle_title_label.pack(pady=(0,1))
        self.current_idle_val_label = ctk.CTkLabel(idle_frame, text="00:00:00", font=self.font_prominent_current_stats, text_color=COLOR_TEXT_PRIMARY)
        self.current_idle_val_label.pack()

    def _create_compact_stats_grid_section(self): # 2x4 grid for 8 stats
        frame=ctk.CTkFrame(self.main_content_frame,fg_color="transparent")
        frame.grid(row=3,column=0,pady=(2,2),padx=15,sticky="nsew")
        frame.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(frame,text="OTHER DAILY STATS",font=self.font_section_titles,text_color=COLOR_TEXT_SECONDARY).pack(pady=(0,2))
        
        grid=ctk.CTkFrame(frame,fg_color="transparent");grid.pack(fill="x",expand=True,padx=10)
        grid.grid_columnconfigure((0,1,2),weight=1) # Keep 3 columns for visual balance, last column can be sparse
        for i in range(3): grid.grid_rowconfigure(i, weight=1) # 3 rows needed for 8 items in 3 cols

        def _cell(r,c,title,attr,is_time=True):
            cell_f=ctk.CTkFrame(grid,fg_color="transparent");cell_f.grid(row=r,column=c,padx=1,pady=1,sticky="nsew")
            cell_f.grid_rowconfigure(0,weight=1); cell_f.grid_rowconfigure(1,weight=1); cell_f.grid_columnconfigure(0,weight=1)
            title_label=ctk.CTkLabel(cell_f,text=title,font=self.font_grid_subtitles,text_color=COLOR_TEXT_SECONDARY)
            title_label.grid(row=0,column=0,sticky="s",pady=(0,0))
            val_lbl=ctk.CTkLabel(cell_f,text="00:00:00"if is_time else"0",font=self.font_grid_counters,text_color=COLOR_TEXT_PRIMARY)
            val_lbl.grid(row=1,column=0,sticky="n",pady=(0,0))
            setattr(self,f"{attr}_grid_title",title_label); setattr(self,f"{attr}_grid_val",val_lbl) # Suffix with _grid

        # Row 0
        _cell(0,0,"TOTAL ACTIVE","total_active_today"); _cell(0,1,"MAX ACTIVE","max_active_today"); _cell(0,2,"PREV. ACTIVE SPELL","prev_active_spell")
        # Row 1
        _cell(1,0,"TOTAL IDLE","total_idle_today"); _cell(1,1,"MAX IDLE","max_idle_today"); _cell(1,2,"PREV. IDLE SPELL","prev_idle_spell")
        # Row 2
        _cell(2,0,"MOUSE DIST. (px)","mouse_dist",False); _cell(2,1,"KEYSTROKES","keystrokes",False); 
        # Cell (2,2) - Mouse clicks counter
        clicks_cell_f = ctk.CTkFrame(grid, fg_color="transparent"); clicks_cell_f.grid(row=2, column=2, padx=1, pady=1, sticky="nsew")
        clicks_cell_f.grid_rowconfigure(0,weight=1); clicks_cell_f.grid_rowconfigure(1,weight=1); clicks_cell_f.grid_columnconfigure(0,weight=1)
        self.mouse_clicks_grid_title = ctk.CTkLabel(clicks_cell_f, text="MOUSE CLICKS", font=self.font_grid_subtitles, text_color=COLOR_TEXT_SECONDARY)
        self.mouse_clicks_grid_title.grid(row=0, column=0, sticky="s")
        self.mouse_clicks_grid_val = ctk.CTkLabel(clicks_cell_f, text="0", font=self.font_grid_counters, text_color=COLOR_TEXT_PRIMARY)
        self.mouse_clicks_grid_val.grid(row=1, column=0, sticky="n")


        btn_style={"font":self.font_buttons,"corner_radius":5,"height":20,"text_color":COLOR_BUTTON_TEXT,"border_width":1,"border_color":"#444","fg_color":COLOR_BUTTON_FG,"hover_color":COLOR_BUTTON_HOVER}
        self.reset_activity_button=ctk.CTkButton(frame,text="RESET DAILY STATS",**btn_style,command=self.reset_daily_activity_counter)
        self.reset_activity_button.pack(pady=(4,2),padx=100,fill="x")


    def _create_pomodoro_settings_info_panel(self):
        # Main panel frame
        panel_frame = ctk.CTkFrame(self.main_content_frame, fg_color=COLOR_MAIN_CONTENT_BG, corner_radius=6)
        panel_frame.grid(row=4, column=0, pady=(2,2), padx=10, sticky="nsew")
        panel_frame.grid_columnconfigure(0, weight=1)

        # Section Title - Reduced vertical padding
        ctk.CTkLabel(panel_frame, text="POMODORO TIMER", font=self.font_section_titles, 
                    text_color=COLOR_TEXT_SECONDARY).grid(row=0, column=0, pady=(2,4), sticky="n")

        # Pomodoro Timer Frame - Tighter spacing
        pomo_display_frame = ctk.CTkFrame(panel_frame, fg_color="transparent")
        pomo_display_frame.grid(row=1, column=0, pady=(0,2), padx=20, sticky="ew")
        pomo_display_frame.grid_columnconfigure((0,1), weight=1)

        # Status and Timer - Tighter vertical spacing
        self.pomodoro_time_label = ctk.CTkLabel(pomo_display_frame, text="00:00", 
                                               font=self.font_pomo_timer_value, 
                                               text_color=COLOR_TEXT_PRIMARY)
        self.pomodoro_time_label.grid(row=0, column=0, columnspan=2, pady=(0,0))
        
        self.pomodoro_status_label = ctk.CTkLabel(pomo_display_frame, text="IDLE", 
                                                 font=self.font_pomo_status, 
                                                 text_color=COLOR_TEXT_SECONDARY)
        self.pomodoro_status_label.grid(row=1, column=0, columnspan=2, pady=(0,2))

        # Control buttons - Reduced height and spacing
        btn_style = {
            "font": self.font_buttons,
            "corner_radius": 4,
            "height": 22,  # Reduced height
            "text_color": COLOR_BUTTON_TEXT,
            "border_width": 1,
            "border_color": "#444",
            "fg_color": COLOR_BUTTON_FG,
            "hover_color": COLOR_BUTTON_HOVER
        }
        
        pomo_controls_frame = ctk.CTkFrame(panel_frame, fg_color="transparent")
        pomo_controls_frame.grid(row=2, column=0, pady=(0,4), padx=20, sticky="ew")
        pomo_controls_frame.grid_columnconfigure((0,1,2), weight=1, uniform="button_col")

        self.pomodoro_start_button = ctk.CTkButton(pomo_controls_frame, text="START", 
                                                  command=self.pomodoro_start_work, **btn_style)
        self.pomodoro_start_button.grid(row=0, column=0, padx=3, sticky="ew")

        self.pomodoro_pause_button = ctk.CTkButton(pomo_controls_frame, text="PAUSE", 
                                                  command=self.pomodoro_pause, state="disabled", **btn_style)
        self.pomodoro_pause_button.grid(row=0, column=1, padx=3, sticky="ew")

        self.pomodoro_reset_button = ctk.CTkButton(pomo_controls_frame, text="RESET", 
                                                  command=self.pomodoro_reset, state="disabled", **btn_style)
        self.pomodoro_reset_button.grid(row=0, column=2, padx=3, sticky="ew")

        # Thinner separator with less padding
        separator = ctk.CTkFrame(panel_frame, height=1, fg_color="#333")
        separator.grid(row=3, column=0, pady=(2,2), padx=20, sticky="ew")

        # Settings Container - Reduced vertical spacing
        settings_info_frame = ctk.CTkFrame(panel_frame, fg_color="transparent")
        settings_info_frame.grid(row=4, column=0, pady=(0,2), padx=20, sticky="ew")
        settings_info_frame.grid_columnconfigure((0,1,2), weight=1)

        # Compact style settings
        entry_style = {
            "font": self.font_settings_entries,
            "border_width": 1,
            "corner_radius": 3,
            "width": 35,
            "height": 20,  # Reduced height
            "justify": "center",
            "border_color": "#444"
        }
        
        label_style = {
            "font": self.font_settings_labels,
            "text_color": COLOR_TEXT_SECONDARY
        }

        apply_btn_style = {
            "font": self.font_buttons,
            "corner_radius": 4,
            "height": 20,  # Reduced height
            "text_color": COLOR_BUTTON_TEXT,
            "border_width": 1,
            "border_color": "#444",
            "fg_color": COLOR_BUTTON_FG,
            "hover_color": COLOR_BUTTON_HOVER,
            "width": 50
        }

        # Settings Grid - Tighter layout
        settings_grid = ctk.CTkFrame(settings_info_frame, fg_color="transparent")
        settings_grid.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0,2))
        settings_grid.grid_columnconfigure((0,1,2,3,4,5), weight=1)

        # Work/Break Settings
        ctk.CTkLabel(settings_grid, text="Work Time:", **label_style).grid(row=0, column=0, padx=(0,1))
        self.work_minutes_entry = ctk.CTkEntry(settings_grid, **entry_style)
        self.work_minutes_entry.insert(0, str(INITIAL_WORK_MINUTES))
        self.work_minutes_entry.grid(row=0, column=1, padx=1)
        
        ctk.CTkLabel(settings_grid, text="Break Time:", **label_style).grid(row=0, column=2, padx=1)
        self.break_minutes_entry = ctk.CTkEntry(settings_grid, **entry_style)
        self.break_minutes_entry.insert(0, str(INITIAL_SHORT_BREAK_MINUTES))
        self.break_minutes_entry.grid(row=0, column=3, padx=1)

        # Inactivity Settings
        ctk.CTkLabel(settings_grid, text="Inactivity Delay:", **label_style).grid(row=0, column=4, padx=1)
        self.inactivity_timeout_entry = ctk.CTkEntry(settings_grid, **entry_style)
        self.inactivity_timeout_entry.insert(0, str(int(_current_inactivity_timeout)))
        self.inactivity_timeout_entry.grid(row=0, column=5, padx=1)

        # Apply Buttons Row
        buttons_frame = ctk.CTkFrame(settings_info_frame, fg_color="transparent")
        buttons_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2,2))
        buttons_frame.grid_columnconfigure((0,1), weight=1)

        self.apply_pomo_settings_button = ctk.CTkButton(buttons_frame, text="APPLY POMODORO", 
                                                       command=self.apply_pomodoro_settings, **apply_btn_style)
        self.apply_pomo_settings_button.grid(row=0, column=0, padx=2, sticky="ew")

        self.apply_inactivity_timeout_button = ctk.CTkButton(buttons_frame, text="APPLY DELAY", 
                                                            command=self.apply_inactivity_timeout_setting, **apply_btn_style)
        self.apply_inactivity_timeout_button.grid(row=0, column=1, padx=2, sticky="ew")

        # Status Info - Compact single row with smaller font
        status_style = {"font": (APP_FONT_FAMILY, 8), "text_color": COLOR_TEXT_SECONDARY}
        status_frame = ctk.CTkFrame(panel_frame, fg_color="transparent")
        status_frame.grid(row=5, column=0, sticky="ew", pady=(0,1))
        status_frame.grid_columnconfigure((0,1,2), weight=1)

        self.app_start_time_label = ctk.CTkLabel(status_frame, text="App: --:--", **status_style)
        self.app_start_time_label.grid(row=0, column=0, sticky="w", padx=5)
        
        self.reset_time_label = ctk.CTkLabel(status_frame, text="Reset: --:--", **status_style)
        self.reset_time_label.grid(row=0, column=1, sticky="", padx=5)
        
        self.pomodoro_start_log_label = ctk.CTkLabel(status_frame, text="Pomo: --:--", **status_style)
        self.pomodoro_start_log_label.grid(row=0, column=2, sticky="e", padx=5)


    def _create_log_console_section(self): # Unchanged
        frame=ctk.CTkFrame(self.main_split,fg_color=COLOR_MAIN_CONTENT_BG,border_color=COLOR_BORDER,border_width=BORDER_THICKNESS,corner_radius=0)
        frame.grid(row=0,column=1,sticky="nsew",padx=(8,0))
        frame.grid_rowconfigure(1,weight=1);frame.grid_columnconfigure(0,weight=1)
        self.log_title_label=ctk.CTkLabel(frame,text="EVENT LOG",font=(APP_FONT_FAMILY,BASE_FONT_SIZE_LOG_TITLE,"bold"),text_color=COLOR_TEXT_SECONDARY);self.log_title_label.grid(row=0,column=0,pady=(6,1),sticky="n")
        self.log_console=ctk.CTkTextbox(frame,fg_color=CONSOLE_BG,text_color=CONSOLE_FG,font=(APP_FONT_FAMILY,CONSOLE_FONT_SIZE),wrap="word",state="disabled");self.log_console.grid(row=1,column=0,sticky="nsew",padx=15,pady=(0,15))

    def on_window_resize_debounced(self, event=None): # Unchanged
        if self._resize_debounce_timer: self.after_cancel(self._resize_debounce_timer)
        self._resize_debounce_timer = self.after(150, lambda e=event: self.on_window_resize(e))

    def on_window_resize(self, event=None): # Updated for new prominent stats labels
        if event and hasattr(event, 'widget') and event.widget != self: return
        try:
            if not self.winfo_exists(): return
            
            # Get current window dimensions and calculate scale
            current_width = self.winfo_width()
            if current_width <= 0: return
            scale = current_width / BASE_WINDOW_WIDTH

            def fs(base, min_s): return max(min_s, int(base * scale))

            self.font_clock=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_CLOCK,MIN_FONT_SIZE_CLOCK),"bold")
            self.font_prominent_current_stats = (APP_FONT_FAMILY, fs(BASE_FONT_SIZE_PROMINENT_CURRENT_STATS, MIN_FONT_SIZE_PROMINENT_CURRENT_STATS), "bold")
            self.font_prominent_stats_subtitle = (APP_FONT_FAMILY, fs(BASE_FONT_SIZE_PROMINENT_STATS_SUBTITLE, MIN_FONT_SIZE_PROMINENT_STATS_SUBTITLE), "normal")
            self.font_effectiveness_value=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_EFFECTIVENESS_VALUE,MIN_FONT_SIZE_EFFECTIVENESS_VALUE),"bold")
            self.font_effectiveness_title=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_EFFECTIVENESS_TITLE,MIN_FONT_SIZE_SECTION_TITLES),"bold")
            self.font_grid_counters=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_GRID_COUNTERS,MIN_FONT_SIZE_GRID_COUNTERS),"bold")
            self.font_grid_subtitles=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_GRID_SUBTITLES,MIN_FONT_SIZE_GRID_SUBTITLES),"normal")
            self.font_pomo_timer_value=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_POMO_TIMER,MIN_FONT_SIZE_POMO_TIMER),"bold")
            self.font_pomo_status=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_POMO_STATUS,MIN_FONT_SIZE_POMO_STATUS),"bold")
            self.font_section_titles=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_SECTION_TITLES,MIN_FONT_SIZE_SECTION_TITLES),"bold")
            self.font_buttons=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_BUTTONS,MIN_FONT_SIZE_BUTTONS),"bold")
            self.font_settings_labels=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_SETTINGS_LABELS,MIN_FONT_SIZE_SETTINGS_LABELS))
            self.font_settings_entries=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_SETTINGS_ENTRIES,MIN_FONT_SIZE_SETTINGS_ENTRIES))
            log_t_fs=(APP_FONT_FAMILY,fs(BASE_FONT_SIZE_LOG_TITLE,10),"bold")

            if hasattr(self,'current_time_label'):self.current_time_label.configure(font=self.font_clock)
            if hasattr(self,'effectiveness_title_label'):self.effectiveness_title_label.configure(font=self.font_effectiveness_title)
            if hasattr(self,'effectiveness_value_label'):self.effectiveness_value_label.configure(font=self.font_effectiveness_value)
            
            # Prominent Current Stats
            if hasattr(self,'current_active_title_label'): self.current_active_title_label.configure(font=self.font_prominent_stats_subtitle)
            if hasattr(self,'current_active_val_label'): self.current_active_val_label.configure(font=self.font_prominent_current_stats)
            if hasattr(self,'current_idle_title_label'): self.current_idle_title_label.configure(font=self.font_prominent_stats_subtitle)
            if hasattr(self,'current_idle_val_label'): self.current_idle_val_label.configure(font=self.font_prominent_current_stats)

            if hasattr(self,'compact_stats_grid_frame'): # Title label of compact stats grid
                for child in self.compact_stats_grid_frame.winfo_children():
                    if isinstance(child,ctk.CTkLabel)and"OTHER DAILY STATS"in child.cget("text"):child.configure(font=self.font_section_titles)
            
            stats_attrs=["total_active_today","max_active_today","prev_active_spell",
                           "total_idle_today","max_idle_today","prev_idle_spell",
                           "mouse_dist","keystrokes", "effectiveness_grid"] # Note: _grid_val and _grid_title suffixes
            for attr_base in stats_attrs:
                attr_val = f"{attr_base}_grid_val"
                attr_title = f"{attr_base}_grid_title"
                if hasattr(self,attr_val)and getattr(self,attr_val).winfo_exists():
                    font_to_use = self.font_grid_counters if attr_base != "effectiveness_grid" else self.font_effectiveness_grid_text
                    getattr(self,attr_val).configure(font=font_to_use)
                if hasattr(self,attr_title)and getattr(self,attr_title).winfo_exists():getattr(self,attr_title).configure(font=self.font_grid_subtitles)

            if hasattr(self,'pomodoro_status_label'):self.pomodoro_status_label.configure(font=self.font_pomo_status)
            if hasattr(self,'pomodoro_time_label'):self.pomodoro_time_label.configure(font=self.font_pomo_timer_value)
            
            btn_s={"font":self.font_buttons};entry_s={"font":self.font_settings_entries};label_s={"font":self.font_settings_labels}
            for btn_n in['reset_activity_button','pomodoro_start_button','pomodoro_pause_button','pomodoro_reset_button','apply_pomo_settings_button','apply_inactivity_timeout_button']:
                if hasattr(self,btn_n)and getattr(self,btn_n).winfo_exists():getattr(self,btn_n).configure(**btn_s)
            for entry_n in['work_minutes_entry','break_minutes_entry','inactivity_timeout_entry']:
                 if hasattr(self,entry_n)and getattr(self,entry_n).winfo_exists():getattr(self,entry_n).configure(**entry_s)
            
            if hasattr(self,'pomodoro_and_settings_panel'):
                panel=self.pomodoro_and_settings_panel
                # Main panel title and section titles within it
                for widget in panel.winfo_children():
                    if isinstance(widget, ctk.CTkLabel) and ("POMODORO & SETTINGS" in widget.cget("text") or "SETTINGS" in widget.cget("text")):
                        widget.configure(font=self.font_section_titles)
                    elif isinstance(widget, ctk.CTkFrame): # Sub-frames like pomo_dur_settings_frame
                        for sub_widget in widget.winfo_children():
                             if isinstance(sub_widget, ctk.CTkLabel) and not isinstance(sub_widget, (ctk.CTkEntry, ctk.CTkButton)):
                                 # Exclude pomo display labels if they have unique fonts, handle app info labels
                                 if sub_widget not in [getattr(self,'pomodoro_status_label',None), getattr(self,'pomodoro_time_label',None),
                                                       getattr(self,'app_start_time_label',None), getattr(self,'reset_time_label',None), getattr(self,'pomodoro_start_log_label',None)]:
                                     if sub_widget.winfo_exists(): sub_widget.configure(font=self.font_settings_labels)
                                 elif sub_widget in [getattr(self,'app_start_time_label',None),getattr(self,'reset_time_label',None),getattr(self,'pomodoro_start_log_label',None)]:
                                     if sub_widget.winfo_exists(): sub_widget.configure(font=self.font_settings_labels) # App info also uses settings_labels font
            if hasattr(self,'log_title_label'):self.log_title_label.configure(font=log_t_fs)
        except Exception as e:print(f"Resize error: {e}\n{traceback.format_exc()}")

    def reset_daily_activity_counter(self):
        now=time.time()
        with state_lock:
            app_state.update({
                "total_active_seconds_today":0.0,"total_idle_seconds_today":0.0,
                "max_idle_seconds_today":0.0,"max_active_seconds_today":0.0,
                "mouse_total_distance_today":0.0,"keystrokes_today":0,
                "mouse_clicks_today":0,  # Reset mouse clicks counter
                "last_activity_duration":0.0, "last_inactivity_duration":0.0,
                "current_idle_start_time":None,"current_activity_start_time":now,
                "last_reset_time":now,"last_activity_time":now,
                "prev_overall_active_state":True,"mouse_last_pos_for_distance":None
            })
        add_log_message(self,"Daily stats reset.")

    def update_gui_display(self):
        if not self.winfo_exists():return
        global _current_inactivity_timeout
        now=time.time();now_dt=datetime.datetime.now()
        if hasattr(self,'current_time_label'):self.current_time_label.configure(text=now_dt.strftime('%H:%M:%S'))
        with state_lock:s=app_state.copy()
        active_s_today=s["total_active_seconds_today"];total_idle_s_today=s["total_idle_seconds_today"]
        active_now=(now-s["last_activity_time"])<_current_inactivity_timeout
        current_idle_s=0.0; current_active_s=0.0
        if active_now:
            if s["current_activity_start_time"]:current_active_s=now-s["current_activity_start_time"]
        else:
            if s["current_idle_start_time"]:current_idle_s=now-s["current_idle_start_time"]
        eff_p=(active_s_today/(active_s_today+total_idle_s_today)*100)if(active_s_today+total_idle_s_today)>0 else 0
        eff_c=COLOR_ACCENT_ACTIVE_MOUSE if eff_p>=50 else COLOR_TEXT_INACTIVE
        if hasattr(self,'effectiveness_value_label'):self.effectiveness_value_label.configure(text=f"{eff_p:.1f}%",text_color=eff_c)
        if hasattr(self,'effectiveness_bar')and self.effectiveness_bar_bg.winfo_exists():
            bar_w=self.effectiveness_bar_bg.winfo_width()-4
            if bar_w>0:self.effectiveness_bar.place_configure(width=max(0,bar_w*(eff_p/100.0)))
            self.effectiveness_bar.configure(fg_color=COLOR_ACCENT_ACTIVE_MOUSE if eff_p>=50 else EFFECTIVENESS_BAR_LOW_COLOR)

        # Prominent Current Stats
        if hasattr(self,'current_active_val_label'):self.current_active_val_label.configure(text=format_hms_string(current_active_s))
        if hasattr(self,'current_active_title_label'):self.current_active_title_label.configure(text_color=COLOR_ACCENT_ACTIVE_MOUSE if active_now and current_active_s > 0.1 else COLOR_TEXT_SECONDARY)
        if hasattr(self,'current_idle_val_label'):self.current_idle_val_label.configure(text=format_hms_string(current_idle_s))
        if hasattr(self,'current_idle_title_label'):self.current_idle_title_label.configure(text_color=COLOR_TEXT_INACTIVE if not active_now and current_idle_s > 0.1 else COLOR_TEXT_SECONDARY)

        # Compact Stats Grid (using _grid_val suffix)
        if hasattr(self,'total_active_today_grid_val'):self.total_active_today_grid_val.configure(text=format_hms_string(active_s_today))
        if hasattr(self,'max_active_today_grid_val'):self.max_active_today_grid_val.configure(text=format_hms_string(s["max_active_seconds_today"]))
        if hasattr(self,'total_idle_today_grid_val'):self.total_idle_today_grid_val.configure(text=format_hms_string(total_idle_s_today))
        if hasattr(self,'max_idle_today_grid_val'):self.max_idle_today_grid_val.configure(text=format_hms_string(s["max_idle_seconds_today"]))
        if hasattr(self,'prev_active_spell_grid_val'):self.prev_active_spell_grid_val.configure(text=format_hms_string(s["last_activity_duration"])if s["last_activity_duration"]>0.1 else"N/A")
        if hasattr(self,'prev_idle_spell_grid_val'):self.prev_idle_spell_grid_val.configure(text=format_hms_string(s["last_inactivity_duration"])if s["last_inactivity_duration"]>0.1 else"N/A")
        if hasattr(self,'mouse_dist_grid_val'):self.mouse_dist_grid_val.configure(text=f"{s['mouse_total_distance_today']:,.0f}")
        if hasattr(self,'keystrokes_grid_val'):self.keystrokes_grid_val.configure(text=f"{s['keystrokes_today']:,}")
        if hasattr(self,'mouse_clicks_grid_val'):self.mouse_clicks_grid_val.configure(text=f"{s.get('mouse_clicks_today', 0):,}")
        if hasattr(self,'effectiveness_grid_val'):self.effectiveness_grid_val.configure(text=f"{eff_p:.1f}%", text_color=eff_c)
        
        p_m=s["pomodoro_mode"];p_rem=s["pomodoro_seconds_remaining"]
        p_d_txt,p_title_c="IDLE",COLOR_TEXT_SECONDARY
        if p_m=="work":p_d_txt,p_title_c="WORK",COLOR_POMO_TIMER_RUNNING
        elif p_m=="break":p_d_txt,p_title_c="BREAK",COLOR_POMO_TIMER_RUNNING
        elif"paused"in p_m:p_d_txt=f"{p_m.split('_')[1].upper()} (PAUSED)"
        if hasattr(self,'pomodoro_status_label'):self.pomodoro_status_label.configure(text=f"{p_d_txt}",text_color=p_title_c)
        if hasattr(self,'pomodoro_time_label'):self.pomodoro_time_label.configure(text=format_ms_string(p_rem))
        if hasattr(self,'reset_time_label'):self.reset_time_label.configure(text=f"Stats Reset: {datetime.datetime.fromtimestamp(s['last_reset_time']).strftime('%H:%M')}"if s['last_reset_time']else"Stats Reset: N/A")
        if hasattr(self,'pomodoro_start_log_label'):self.pomodoro_start_log_label.configure(text=f"Pomo Last Start: {datetime.datetime.fromtimestamp(s['pomodoro_start_time']).strftime('%H:%M')}"if s['pomodoro_start_time']>0 else"Pomo Last Start: N/A")
        if hasattr(self,'app_start_time_label'):self.app_start_time_label.configure(text=f"App Started: {self.app_start_time_dt.strftime('%H:%M:%S')}")
        if s["running"]:self.after(int(ACTIVITY_CHECK_INTERVAL*1000),self.update_gui_display)

    def apply_pomodoro_settings(self): # Unchanged
        try:
            w_m,b_m=int(self.work_minutes_entry.get()),int(self.break_minutes_entry.get())
            if not(0<w_m<1000 and 0<b_m<1000):raise ValueError("Durations out of range.")
            with state_lock:
                app_state.update({"pomodoro_work_duration_seconds":w_m*60,"pomodoro_break_duration_seconds":b_m*60})
                if app_state["pomodoro_mode"]=="idle":app_state["pomodoro_seconds_remaining"]=app_state["pomodoro_work_duration_seconds"]
            add_log_message(self,f"Pomo: Work {w_m}m, Break {b_m}m")
        except Exception as e:add_log_message(self,f"Pomo settings error: {e}")
    def apply_inactivity_timeout_setting(self): # Unchanged
        global _current_inactivity_timeout
        try:
            new_timeout=float(self.inactivity_timeout_entry.get())
            if not(1.0<=new_timeout<=3600.0):raise ValueError("Timeout 1-3600s.")
            _current_inactivity_timeout=new_timeout
            add_log_message(self,f"Inactivity timeout: {_current_inactivity_timeout:.1f}s.")
        except Exception as e:
            add_log_message(self,f"Timeout error: {e}")
            self.inactivity_timeout_entry.delete(0,"end");self.inactivity_timeout_entry.insert(0,str(int(_current_inactivity_timeout)))
    def pomodoro_start_work(self):self._pomodoro_action("work") # Unchanged
    def pomodoro_start_break(self):self._pomodoro_action("break") # Unchanged
    def _pomodoro_action(self,mode_to_start): # Unchanged
        with state_lock:
            p_sec=app_state[f"pomodoro_{mode_to_start}_duration_seconds"]
            app_state.update({"pomodoro_mode":mode_to_start,"pomodoro_seconds_remaining":p_sec,"pomodoro_start_time":time.time()})
        add_log_message(self,f"Pomo {mode_to_start} ({int(p_sec/60)}m) started.")
        self.update_pomodoro_buttons()
    def pomodoro_pause(self): # Unchanged
        with state_lock:
            mode=app_state["pomodoro_mode"]
            if mode not in["work","break"]:return
            app_state.update({"pomodoro_mode":f"paused_{mode}","pomodoro_paused_seconds_remaining":app_state["pomodoro_seconds_remaining"],"pomodoro_start_time":0})
        add_log_message(self,f"Pomo {mode} paused.")
        self.update_pomodoro_buttons()
    def pomodoro_resume(self): # Unchanged
         with state_lock:
            mode=app_state["pomodoro_mode"];
            if not mode.startswith("paused_"):return
            target_mode=mode.split("_")[1] 
            paused_rem=app_state["pomodoro_paused_seconds_remaining"]
            full_dur=app_state[f"pomodoro_{target_mode}_duration_seconds"]
            start_time=time.time()-(full_dur-paused_rem)
            app_state.update({"pomodoro_mode":target_mode,"pomodoro_seconds_remaining":paused_rem,"pomodoro_start_time":start_time})
         add_log_message(self,f"Pomo {target_mode} resumed.")
         self.update_pomodoro_buttons()
    def pomodoro_reset(self): # Unchanged
        with state_lock:app_state.update({"pomodoro_mode":"idle","pomodoro_seconds_remaining":app_state["pomodoro_work_duration_seconds"],"pomodoro_start_time":0,"pomodoro_paused_seconds_remaining":0})
        add_log_message(self,"Pomo timer reset.")
        self.update_pomodoro_buttons()
    def update_pomodoro_buttons(self): # Unchanged
        if not self.winfo_exists():return
        with state_lock:mode=app_state["pomodoro_mode"]
        is_idle,is_running,is_paused=mode=="idle",mode in["work","break"],mode.startswith("paused_")
        start_txt,start_cmd,start_st="START",self.pomodoro_start_work,"disabled"
        if is_idle:start_st="normal"
        elif is_paused:start_txt,start_cmd,start_st="RESUME",self.pomodoro_resume,"normal"
        try:
            if hasattr(self,'pomodoro_start_button'):self.pomodoro_start_button.configure(text=start_txt,command=start_cmd,state=start_st)
            if hasattr(self,'pomodoro_pause_button'):self.pomodoro_pause_button.configure(state="normal"if is_running else"disabled")
            if hasattr(self,'pomodoro_reset_button'):self.pomodoro_reset_button.configure(state="normal"if(is_running or is_paused)else"disabled")
        except Exception as e:print(f"Error updating pomo buttons: {e}")

    def tracking_loop(self): # Logic for current/previous active/idle spells updated
        global _current_inactivity_timeout
        last_save,last_inactivity_log=time.time(),0
        while True:
            with state_lock:running=app_state["running"]
            if not running:break
            now=time.time()
            today_iso=datetime.date.today().isoformat()
            with state_lock:current_day_s=app_state["current_day_string"]
            if current_day_s!=today_iso: 
                add_log_message(self,f"Day change: {today_iso}. Resetting counters.")
                save_daily_data()
                with state_lock:
                    app_state.update({
                        "current_day_string":today_iso,
                        "total_active_seconds_today":0.0,"total_idle_seconds_today":0.0,
                        "max_idle_seconds_today":0.0,"max_active_seconds_today":0.0,
                        "mouse_total_distance_today":0.0,"keystrokes_today":0,
                        "last_activity_duration":0.0, "last_inactivity_duration":0.0,
                        "current_idle_start_time":None,"current_activity_start_time":now,
                        "last_reset_time":None,"prev_overall_active_state":True,
                        "last_activity_time":now,"mouse_last_pos_for_distance":None
                    })
                load_daily_data() 
            with state_lock: 
                s_trk=app_state;last_act_time=s_trk["last_activity_time"];was_active=s_trk["prev_overall_active_state"]
                cur_idle_start_ts=s_trk["current_idle_start_time"];cur_act_start_ts=s_trk["current_activity_start_time"]
                cur_max_idle=s_trk["max_idle_seconds_today"];cur_max_active=s_trk["max_active_seconds_today"]
            active_now=(now-last_act_time)<_current_inactivity_timeout
            updates={};log_msg=None
            if was_active and not active_now: 
                updates["current_idle_start_time"] = last_act_time 
                if cur_act_start_ts is not None: 
                    act_dur = last_act_time - cur_act_start_ts
                    if act_dur > 0:
                        updates["last_activity_duration"] = act_dur 
                        updates["max_active_seconds_today"] = max(cur_max_active, act_dur)
                updates["current_activity_start_time"] = None 
                log_msg = "Became inactive."
            elif not was_active and active_now: 
                updates["current_activity_start_time"] = now 
                if cur_idle_start_ts is not None: 
                    idle_dur = now - cur_idle_start_ts 
                    if idle_dur > 1.0:
                        updates["last_inactivity_duration"] = idle_dur 
                        if idle_dur > cur_max_idle: updates["max_idle_seconds_today"] = idle_dur
                        log_msg = f"Active after {format_hms_string(idle_dur)} idle."
                    else: log_msg = "Active (short idle)."
                else: log_msg = "Became active."
                updates["current_idle_start_time"] = None 
            with state_lock: 
                 app_state.update(updates)
                 if active_now:app_state["total_active_seconds_today"]+=ACTIVITY_CHECK_INTERVAL
                 elif app_state["current_idle_start_time"]is not None:app_state["total_idle_seconds_today"]+=ACTIVITY_CHECK_INTERVAL
                 app_state["prev_overall_active_state"]=active_now
            if log_msg:add_log_message(self,log_msg)
            current_inactive_seconds_for_log = 0 if active_now else (now - app_state.get("current_idle_start_time", now))
            if not active_now and current_inactive_seconds_for_log >=LONG_INACTIVITY_THRESHOLD and(now-last_inactivity_log>=LONG_INACTIVITY_THRESHOLD):
                add_log_message(self,f"Still inactive ({round(current_inactive_seconds_for_log/60)}m)");last_inactivity_log=now
            elif active_now:last_inactivity_log=0
            with state_lock: 
                p_m=app_state["pomodoro_mode"];p_st=app_state["pomodoro_start_time"]
                p_wd=app_state["pomodoro_work_duration_seconds"];p_bd=app_state["pomodoro_break_duration_seconds"]
            if p_m in["work","break"]and p_st>0:
                el_p=now-p_st;cur_p_d=p_wd if p_m=="work"else p_bd;rem_p=max(0,cur_p_d-el_p)
                proc=False
                with state_lock:
                    if app_state["pomodoro_seconds_remaining"]==-1 or app_state["pomodoro_start_time"]==0:proc=True
                    if not proc:app_state["pomodoro_seconds_remaining"]=rem_p
                if not proc and rem_p<=0:
                    with state_lock:cur_m_fin=app_state["pomodoro_mode"];app_state.update({"pomodoro_seconds_remaining":-1,"pomodoro_start_time":0})
                    next_act=self.pomodoro_start_break if cur_m_fin=="work"else self.pomodoro_start_work
                    log_p=f"Pomo {cur_m_fin} done. Starting {'break'if cur_m_fin=='work'else'work'}.";add_log_message(self,log_p);self.after(0,next_act)
            if now-last_save>60:save_daily_data();last_save=now
            time.sleep(max(0,ACTIVITY_CHECK_INTERVAL-(time.time()-now)))
        print("Tracking loop finished.")

    def start_mouse_listener(self):
        try:
            threading.Thread(target=pynput.mouse.Listener(on_move=on_move, on_click=on_click).start,
                           daemon=True, name="MouseListener").start()
        except Exception as e:
            add_log_message(self,f"Mouse listener error: {e}")
    def start_keyboard_listener(self): # Unchanged
        try:threading.Thread(target=pynput.keyboard.Listener(on_press=on_key_press).start,daemon=True,name="KeyboardListener").start()
        except Exception as e:add_log_message(self,f"Keyboard listener error: {e}")
    def start_tracking_loop(self): # Unchanged
        try:self.tracking_thread=threading.Thread(target=self.tracking_loop,daemon=True,name="TrackingLoop");self.tracking_thread.start()
        except Exception as e:add_log_message(self,f"Tracking loop error: {e}")
    def on_closing(self): # Unchanged
        add_log_message(self,"Shutdown initiated...")
        with state_lock:app_state["running"]=False
        if hasattr(self,'tracking_thread')and self.tracking_thread.is_alive():
            add_log_message(self,"Waiting for tracking loop...");self.tracking_thread.join(timeout=0.5)
        add_log_message(self,"Final save...");save_daily_data()
        add_log_message(self,"Exiting.");print("App closed.")
        self.destroy()

if __name__=="__main__":
    try:
        if hasattr(sys,'_MEIPASS'):os.chdir(sys._MEIPASS)
        elif"__file__"in locals()or"__file__"in globals():os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except Exception as e:print(f"CWD Error: {e}")
    Image=None 
    try:from PIL import Image
    except ImportError:
        Image = None
        print("Pillow (PIL) not found. PNG icons might not work.")
    app=DominantBorderHubApp()
    app.mainloop()