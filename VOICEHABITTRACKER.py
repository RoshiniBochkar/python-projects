import speech_recognition as sr
import spacy
import datetime
import threading
import re
import os
import platform
import tkinter as tk
from tkinter import messagebox
from tkinter.filedialog import asksaveasfilename
import pygame  # Import pygame for playing MP3 files
import ttkbootstrap as ttkb  # Import ttkbootstrap for themes

# Load NLP model
nlp = spacy.load("en_core_web_sm")

# List to store active alarms
active_alarms = []
alarm_history = []  # List to store alarm history
current_alarm_thread = None  # Store the current alarm thread for snooze/stop functionality

# Initialize pygame mixer
pygame.mixer.init()

def clean_time_string(time_str):
    """Extracts and formats the time string from speech."""
    time_str = time_str.lower().replace("in the morning", "AM").replace("in the evening", "PM")
    time_str = re.sub(r"(\d+)(a\.m\.|p\.m\.)", r"\1 \2", time_str)  # Ensure space before AM/PM
    time_str = time_str.replace("a.m.", "AM").replace("p.m.", "PM").strip()

    match = re.search(r"(\d{1,2}(:\d{2})?\s?(AM|PM))", time_str, re.IGNORECASE)
    return match.group(1) if match else None

def extract_time_and_task(text):
    """Extracts time and task using NLP."""
    doc = nlp(text)
    time_entity = None
    task_words = []

    for ent in doc.ents:
        if ent.label_ in ["TIME", "DATE"]:
            time_entity = clean_time_string(ent.text)

    for token in doc:
        if token.pos_ in ["NOUN", "VERB"] and token.text.lower() not in ["set", "alarm", "reminder", "for"]:
            task_words.append(token.text)

    task = " ".join(task_words) if task_words else "Reminder"
    return time_entity, task

def play_buzzer():
    """Plays a custom alarm sound (alarm1.mp3) on all platforms."""
    system_name = platform.system()
    
    try:
        # Load and play the alarm sound in a loop
        pygame.mixer.music.load("alarm2.wav")  # Path to your alarm1.mp3 file
        pygame.mixer.music.play(loops=-1)  # Loop indefinitely
        
    except Exception as e:
        print(f"Error playing sound: {e}")

def stop_buzzer():
    """Stops the alarm sound."""
    pygame.mixer.music.stop()

def trigger_alarm(task):
    """Triggers the alarm with a custom alarm sound."""
    # Play the alarm sound first
    play_buzzer()

    # Then show the message box
    result = messagebox.showinfo("Alarm", f"⏰ Alarm: {task} 🚨\n\nClick OK to stop the alarm.")

    # Stop the alarm sound when the user clicks OK
    if result == "ok":
        stop_buzzer()

    # Show the snooze and stop controls
    show_alarm_controls(task)

def show_alarm_controls(task):
    """Shows the snooze and stop controls when the alarm is triggered."""
    snooze_button.pack(pady=5)
    stop_button.pack(pady=5)
    snooze_button.config(command=lambda: snooze_alarm(task))
    stop_button.config(command=stop_alarm)

def stop_alarm():
    """Stops the alarm by hiding the snooze and stop buttons."""
    snooze_button.pack_forget()
    stop_button.pack_forget()
    messagebox.showinfo("Alarm Stopped", "The alarm has been stopped.")

def snooze_alarm(task):
    """Snoozes the alarm for 5 minutes."""
    snooze_button.pack_forget()  # Hide the snooze button after use
    stop_button.pack_forget()  # Hide the stop button after use
    messagebox.showinfo("Snoozed", "The alarm has been snoozed for 5 minutes.")
    
    # Schedule the alarm to trigger again in 5 minutes
    threading.Timer(5 * 60, lambda: trigger_alarm(task)).start()  # 5 minutes delay

def schedule_alarm(task, alarm_time):
    """Schedules an alarm at the specified time."""
    try:
        alarm_time_obj = datetime.datetime.strptime(alarm_time, "%I:%M %p")
        now = datetime.datetime.now()
        alarm_time_obj = alarm_time_obj.replace(year=now.year, month=now.month, day=now.day)

        if alarm_time_obj < now:
            alarm_time_obj += datetime.timedelta(days=1)  # If time has passed, schedule for next day

        delay = (alarm_time_obj - now).total_seconds()
        global current_alarm_thread
        current_alarm_thread = threading.Timer(delay, lambda: trigger_alarm(task))
        current_alarm_thread.start()
        active_alarms.append((task, alarm_time))
        alarm_history.append((task, alarm_time))  # Add to history
        update_alarm_list()
        messagebox.showinfo("Alarm Set", f"Task: {task}\nTime: {alarm_time}")
    except ValueError:
        messagebox.showerror("Error", f"Could not parse time format: {alarm_time}")

def recognize_speech():
    """Listens to live speech and processes it."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        status_label.config(text="Listening...")
        recognizer.adjust_for_ambient_noise(source)
        try:
            audio = recognizer.listen(source)
            text = recognizer.recognize_google(audio)
            status_label.config(text=f"You said: {text}")

            time_entity, task = extract_time_and_task(text)
            if time_entity and task:
                schedule_alarm(task, time_entity)
            else:
                messagebox.showwarning("Error", "Could not extract time and task properly.")
        except sr.UnknownValueError:
            messagebox.showerror("Error", "Could not understand audio.")
        except sr.RequestError:
            messagebox.showerror("Error", "Speech recognition service error.")

def update_alarm_list():
    """Updates the alarm list in the GUI."""
    alarm_listbox.delete(0, tk.END)
    for alarm in active_alarms:
        alarm_listbox.insert(tk.END, f"{alarm[0]} - {alarm[1]}")

def remove_selected_alarm():
    """Removes the selected alarm."""
    global active_alarms
    selected_idx = alarm_listbox.curselection()
    if selected_idx:
        active_alarms.pop(selected_idx[0])
        update_alarm_list()
    else:
        messagebox.showwarning("Warning", "Select an alarm to remove.")

def save_alarm_history():
    """Saves the alarm history to a text file."""
    file_path = asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
    if file_path:
        try:
            with open(file_path, "w") as file:
                for alarm in alarm_history:
                    file.write(f"{alarm[0]} - {alarm[1]}\n")
            messagebox.showinfo("Success", "Alarm history saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while saving the file: {e}")

# Tkinter UI Setup with ttkbootstrap (Superhero theme)
root = ttkb.Window(themename="superhero")  # Use the 'superhero' theme
root.title("Voice-Controlled Alarm App")
root.geometry("400x600")

ttkb.Label(root, text="Voice-Controlled Alarm", font=("Arial", 14, "bold")).pack(pady=10)

status_label = ttkb.Label(root, text="Press to start listening", font=("Arial", 10))
status_label.pack()

ttkb.Button(root, text="🎙 Speak", command=recognize_speech, style="success.TButton", bootstyle="primary").pack(pady=5)

ttkb.Label(root, text="Active Alarms:", font=("Arial", 12, "bold")).pack(pady=5)

alarm_listbox = tk.Listbox(root, width=40, height=10)
alarm_listbox.pack(pady=5)

ttkb.Button(root, text="Remove Alarm", command=remove_selected_alarm, bootstyle="danger").pack(pady=5)

# Add button to save alarm history
ttkb.Button(root, text="Save Alarm History", command=save_alarm_history, bootstyle="info").pack(pady=5)

# Add Snooze and Stop buttons
snooze_button = ttkb.Button(root, text="Snooze for 5 minutes", style="secondary.TButton")
stop_button = ttkb.Button(root, text="Stop Alarm", style="danger.TButton")

root.mainloop()