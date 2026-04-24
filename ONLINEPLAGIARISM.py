import os
import difflib
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from tkinter import ttk
from ttkthemes import ThemedTk

class FileComparerApp:
    def __init__(self, root):
        self.root = root
        self.root.set_theme('black')
        self.root.title("MRU Plagiarism")
        self.root.geometry("800x600")
        self.root.state('zoomed')

        self.files = []
        self.result_text = None

        self.setup_gui()

    def compare_files(self, file1, file2):
        try:
            with open(file1, 'r') as f1, open(file2, 'r') as f2:
                text1 = f1.read()
                text2 = f2.read()

                matcher = difflib.SequenceMatcher(None, text1, text2)
                similarity_ratio = matcher.ratio()

                return os.path.basename(file1), os.path.basename(file2), similarity_ratio
        except Exception as e:
            messagebox.showerror("Error", f"Error comparing files: {str(e)}")

    def generate_report(self):
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete('1.0', tk.END)

        for i in range(len(self.files)):
            for j in range(i + 1, len(self.files)):
                file1 = self.files[i]
                file2 = self.files[j]
                file1_name, file2_name, similarity_ratio = self.compare_files(file1, file2)

                result_line = f"{file1_name} vs {file2_name}: {similarity_ratio:.2%}\n"

                if similarity_ratio > 0.6:
                    # Highlight lines with similarity ratio above 60% in red
                    self.result_text.insert(tk.END, result_line, 'red')
                else:
                    self.result_text.insert(tk.END, result_line)

        self.result_text.config(state=tk.DISABLED)

    def add_files(self):
        self.files.extend(filedialog.askopenfilenames(filetypes=[("Text Files", "*.txt")]))
        if self.files:
            self.file_listbox.delete(0, tk.END)
            for file in self.files:
                self.file_listbox.insert(tk.END, os.path.basename(file))

    def download_report(self):
        report_content = self.result_text.get('1.0', tk.END)
        if not report_content.strip():
            messagebox.showinfo("No Report", "No report generated to download.")
            return

        report_filename = "comparison_report.txt"
        try:
            with open(report_filename, 'w') as report_file:
                report_file.write(report_content)

            messagebox.showinfo("Report Downloaded", f"Comparison report downloaded successfully: {report_filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Error downloading report: {str(e)}")

    def setup_gui(self):
        title_label = ttk.Label(self.root, text="MRU Plagiarism", font=("IMPACT", 20, "bold"), anchor="center")
        title_label.pack(side="top", fill="both", pady=(10, 10))

        frame = ttk.Frame(self.root, padding="10", style="Custom.TFrame")
        frame.pack(side="top", fill="both", expand=True)
        frame.configure(style="Custom.TFrame")

        self.file_listbox = tk.Listbox(frame, selectmode=tk.MULTIPLE, bd=2, relief=tk.SOLID)
        self.file_listbox.grid(row=0, column=0, columnspan=3, pady=(10, 10), padx=(10, 10), sticky="nsew")

        add_button = ttk.Button(frame, text="Add Files", command=self.add_files, style="Custom.TButton")
        add_button.grid(row=1, column=0, pady=(0, 10), padx=(10, 10), sticky="nsew")

        compare_button = ttk.Button(frame, text="Generate Report", command=self.generate_report, style="Custom.TButton")
        compare_button.grid(row=1, column=1, pady=(0, 10), padx=(10, 10), sticky="nsew")

        download_button = ttk.Button(frame, text="Download Report", command=self.download_report, style="Custom.TButton")
        download_button.grid(row=1, column=2, pady=(0, 10), padx=(10, 10), sticky="nsew")

        self.result_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, width=50, height=15, bd=2, relief=tk.SOLID)
        self.result_text.grid(row=2, column=0, columnspan=3, pady=(0, 10), padx=(10, 10), sticky="nsew")
        self.result_text.config(state=tk.DISABLED)

        # Set up tag for highlighting
        self.result_text.tag_configure('red', foreground='red')

        # Set up resizing behavior
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=1)

if __name__ == "__main__":
    root = ThemedTk(theme="adapta")  # Use a light blue theme; you can change it to another light theme if needed
    app = FileComparerApp(root)
    root.mainloop()