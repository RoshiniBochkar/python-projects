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
    
    # remove am/pm first
    clean_text = re.sub(r"\b(a\.m\.|p\.m\.|AM|PM|am|pm|a.m|p.m)\b", "", text)

    doc = nlp(text)  # use original for time extraction
    time_entity = None

    # extract time
    for ent in doc.ents:
        if ent.label_ in ["TIME", "DATE"]:
            time_entity = clean_time_string(ent.text)

    # now extract from cleaned text
    doc2 = nlp(clean_text)
    task_words = []

    for token in doc2:
        if (token.pos_ in ["NOUN", "VERB"]
            and token.text.lower() not in ["set", "alarm", "reminder", "for", "at", "on", "me", "wake", "up"]
            and not any(char.isdigit() for char in token.text)):
            task_words.append(token.text)

    task = " ".join(task_words) if task_words else "Reminder"
    return time_entity, task

def play_buzzer():
    """Plays a custom alarm sound (alarm1.mp3) on all platforms."""
    try:
        pygame.mixer.music.load("alarm2.wav")
        pygame.mixer.music.play(loops=-1)
    except Exception as e:
        print(f"Error playing sound: {e}")

def stop_buzzer():
    """Stops the alarm sound."""
    pygame.mixer.music.stop()

def trigger_alarm(task):
    """Triggers the alarm with a custom alarm sound."""
    play_buzzer()
    result = messagebox.showinfo("Alarm", f"⏰ Alarm: {task} 🚨\n\nClick OK to stop the alarm.")
    if result == "ok":
        stop_buzzer()
    show_alarm_controls(task)

def show_alarm_controls(task):
    snooze_button.pack(pady=5)
    stop_button.pack(pady=5)
    snooze_button.config(command=lambda: snooze_alarm(task))
    stop_button.config(command=stop_alarm)

def stop_alarm():
    snooze_button.pack_forget()
    stop_button.pack_forget()
    messagebox.showinfo("Alarm Stopped", "The alarm has been stopped.")

def snooze_alarm(task):
    snooze_button.pack_forget()
    stop_button.pack_forget()
    messagebox.showinfo("Snoozed", "The alarm has been snoozed for 5 minutes.")
    threading.Timer(5 * 60, lambda: trigger_alarm(task)).start()

def schedule_alarm(task, alarm_time):
    try:
        alarm_time_obj = datetime.datetime.strptime(alarm_time, "%I:%M %p")
        now = datetime.datetime.now()
        alarm_time_obj = alarm_time_obj.replace(year=now.year, month=now.month, day=now.day)

        if alarm_time_obj < now:
            alarm_time_obj += datetime.timedelta(days=1)

        delay = (alarm_time_obj - now).total_seconds()
        global current_alarm_thread
        current_alarm_thread = threading.Timer(delay, lambda: trigger_alarm(task))
        current_alarm_thread.start()
        active_alarms.append((task, alarm_time))
        alarm_history.append((task, alarm_time))
        update_alarm_list()
        messagebox.showinfo("Alarm Set", f"Task: {task}\nTime: {alarm_time}")
    except ValueError:
        messagebox.showerror("Error", f"Could not parse time format: {alarm_time}")

def recognize_speech():
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
    alarm_listbox.delete(0, tk.END)
    for alarm in active_alarms:
        alarm_listbox.insert(tk.END, f"{alarm[0]} - {alarm[1]}")

def remove_selected_alarm():
    global active_alarms
    selected_idx = alarm_listbox.curselection()
    if selected_idx:
        active_alarms.pop(selected_idx[0])
        update_alarm_list()
    else:
        messagebox.showwarning("Warning", "Select an alarm to remove.")

def save_alarm_history():
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
root = ttkb.Window(themename="superhero")
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

ttkb.Button(root, text="Save Alarm History", command=save_alarm_history, bootstyle="info").pack(pady=5)

snooze_button = ttkb.Button(root, text="Snooze for 5 minutes", style="secondary.TButton")
stop_button = ttkb.Button(root, text="Stop Alarm", style="danger.TButton")

root.mainloop()