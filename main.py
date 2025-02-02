import tkinter as tk
from tkinter import filedialog
import requests
import pdfkit
from bs4 import BeautifulSoup
import re
from collections import defaultdict
import os
import platform
import json

api_url = "https://scan-app-9206bf041b06.herokuapp.com/api/questions?question_filter=true"
BACKUP_SAVE_URL = "https://backup-questions-e95023d8185c.herokuapp.com/backup"
DELETE_API_URL = "https://scan-app-9206bf041b06.herokuapp.com/api/questions"

def get_questions_from_api(url):
    try:
        response = requests.get(api_url)
        response.raise_for_status()  # Xatoliklarni ushlash
        json_response = response.json()

        if isinstance(json_response, list):  # Ro'yxat kelayotganini tekshiramiz
            data = json_response  # To'g'ridan-to'g'ri ro'yxatni olish
        elif isinstance(json_response, dict) and "data" in json_response:
            data = json_response["data"]  # Agar lug‘at bo‘lsa, "data" ni olish
        else:
            print("Noma'lum API javobi:", json_response)
            return None
        return data
    except requests.exceptions.RequestException as e:
        print(f"GET so'rovida xatolik: {e}")
        return None
    
def send_question_data_to_database_sync(questions_data): 
    """Savol ma'lumotlarini BackupDataView orqali bazaga yuborish (sinxron versiya).
    Ma'lumotlar to'g'ridan-to'g'ri JSON array shaklida yuboriladi, ya'ni "data" kaliti bo'lmaydi. 
    """
    formatted_data = []

    # Har bir itemni ko'rib chiqamiz
    for item in questions_data:    
        list_id = item.get("list_id")
        questions = item.get("questions", [])
        for question in questions:
            true_answer = question.get("true_answer")
            order = question.get("order")
            if list_id is None or order is None:
                print("Xatolik: 'list' va 'order' maydonlari talab qilinadi.")
                continue  # Xato ma'lumotlarni o'tkazib yuboramiz
            
            formatted_item = {
                "list_id": list_id,
                "true_answer": true_answer,
                "order": order
            }
            formatted_data.append(formatted_item)

        if not formatted_data:
            print("Hech qanday savol saqlanmadi.")
            return {"error": "Hech qanday savol saqlanmadi."}

    try:
        # JSON obyektini qo'lda yaratamiz: (bu yerda to'g'ridan-to'g'ri ro'yxat yuboriladi)
        payload = json.dumps(formatted_data)
        headers = {'Content-Type': 'application/json'}
        print("Yuborilayotgan data:", payload)
        response = requests.post(BACKUP_SAVE_URL, data=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        # print("Ma'lumotlar muvaffaqiyatli saqlandi:", result)
        return {"success": True, "data": result}
    except requests.exceptions.RequestException as e:
        print(f"POST so'rovida xatolik: {e}")
        return {"error": "Ma'lumotlarni saqlashda xatolik yuz berdi."}
    
def delete_questions_after_completion_sync():
    """Savollarni o'chirish uchun DELETE so'rovini yuborish (sinxron versiya)"""
    try:
        response = requests.delete(DELETE_API_URL)
        if response.status_code == 200:
            print("Barcha savollar muvaffaqiyatli o'chirildi.")
        else:
            print(f"Ma'lumotlarni o'chirishda xatolik: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"DELETE so'rovida xatolik: {e}")


def clean_html_and_remove_numbers(html_text, order):
    soup = BeautifulSoup(html_text, "html.parser")
    for text_element in soup.find_all(string=True):
        if text_element.parent.name not in ["img"]:
            cleaned_text = re.sub(r'^\s*\d+[\.\)\:\-]\s*', '', text_element)
            cleaned_text = f"{order}. {cleaned_text}" if order else cleaned_text
            text_element.replace_with(cleaned_text)
    return str(soup)

def generate_category_tablee(questions, grade):  # Ikkita argument qabul qilish
    # grade ni int ga aylantiramiz
    try:
        grade = int(grade)
    except ValueError:
        return "<p>Xato: Sinf raqami raqam ko'rinishida emas.</p>"
        
    category_subject_mapping = {}
    for question in questions:
        category = question.get('category', 'Nomalum kategoriya')
        subject = question.get('subject', 'Nomalum fan')
        category_subject_mapping[category] = subject

    # Sinfga qarab kategoriya va fanlarni ajratish
    if 5 <= grade <= 8:
        # Agar past sinflar uchun API kalitlari shu formatda bo'lsa (agar bo'lmasa, shunchaki moslang)
        ranges = [
            ("31-60", "Fan_1"),
            ("61-90", "Fan_2")
        ]
    elif 9 <= grade <= 11:
        ranges = [
            ("1-10", "Majburiy_Fan_1"),
            ("11-20", "Majburiy_Fan_2"),
            ("21-30", "Majburiy_Fan_3"),
            ("31-60", "Fan_1"),
            ("61-90", "Fan_2")
        ]
    else:
        return "<p>Xato: Noto'g'ri sinf raqami.</p>"

    html = """
    <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-family: Times, serif;">
        <thead>
            <tr>
                <th style="border: 1px solid #000; padding: 8px; width: 30%;">Savollar soni</th>
                <th style="border: 1px solid #000; padding: 8px; width: 40%;">Kategoriya</th>
                <th style="border: 1px solid #000; padding: 8px; width: 30%;">Fan nomi</th>
            </tr>
        </thead>
        <tbody>
    """
    for savol_soni, kategoriya in ranges:
        fan_nomi = category_subject_mapping.get(kategoriya, 'Fan nomi mavjud emas')
        html += f"""
            <tr>
                <td style='border: 1px solid #000; padding: 8px; text-align: center;'>{savol_soni}</td>
                <td style='border: 1px solid #000; padding: 8px; text-align: center;'>{kategoriya}</td>
                <td style='border: 1px solid #000; padding: 8px; text-align: center;'>{fan_nomi}</td>
            </tr>
        """
    html += """</tbody></table>"""
    return html






def generate_cover_page_content(grade, list_id, question_class):
    """
    PDF ning cover (kirish) sahifasini HTML formatida yaratadi.
    
    Parametrlar:
      - grade: sinf raqami (API-dan kelgan "question_class" asosida aniqlanadi)
      - list_id: kitob raqami (raqam formatida chiqarish uchun zfill ishlatiladi)
      - question_class: API'dan kelgan savollar yoki kategoriya ma'lumotlari
    """
    # grade ni int ga aylantirishga harakat qilamiz
    try:
        grade_int = int(grade)
    except ValueError:
        grade_int = 0

    # grade asosida imtihon vaqtini aniqlaymiz:
    if 5 <= grade_int <= 8:
        exam_time = "2 soat"
    elif 9 <= grade_int <= 11:
        exam_time = "3 soat"
    else:
        exam_time = "Noma'lum vaqt"

    cover_html = f"""
    <div style="position: relative; height: 297mm; font-family: 'Times New Roman';">
        <img src="https://scan-app-uploads.s3.eu-north-1.amazonaws.com/2+(1).jpg" 
             style="width: 80%; margin: 0 auto; display: block; position: absolute; top: 0px; left: 10%;" />
        <div style="position: absolute; top: 320px; left: 10%; width: 80%; text-align: center;">
            <div style="font-size: 16pt; margin-bottom: 8px;">Qashqadaryo viloyati Guzor tuman "Buxoro qorako'l"</div>
            <div style="font-size: 16pt; margin-bottom: 20px;">xususiy maktabining savollar kitobi</div>
            <div style="font-size: 14pt; margin-bottom: 10px;">Oliy ta'lim muassasalariga kiruvchilar uchun</div>
            <div style="font-size: 14pt; margin-bottom: 20px;">Savollar kitobi {grade}-sinf</div>
            <div style="font-size: 14pt; margin-bottom: 30px;">Savollar kitobi raqami: {str(list_id).zfill(6)}</div>
        </div>
        <div style="position: absolute; top: 600px; left: 10%; width: 80%;">
            {generate_category_tablee(question_class, grade)}
        </div>
        <div style="position: absolute; bottom: 30px; left: 10%; width: 80%; font-size: 12pt;">
            <div style="text-align: center; margin-bottom: 10px; font-weight: bold;">
                Test bajaruvchi uchun yo'riqnoma:
            </div>
            <div style="line-height: 1.5;">
                1. Test topshiriqlarini bajarish uchun berilgan vaqt {exam_time};<br>
                2. Savollar kitobini o'zingiz bilan olib ketishingiz va o'z ustingizda ishlashingiz mumkin;<br>
                3. Javoblar varaqasini e'tibor bilan bo'yashingiz shart;<br>
                4. Test natijalari 5 ish kuni davomida e'lon qilinadi;<br>
                5. Natijalar @bukhara_maktabi_bot rasmiy telegram boti orqali bilib olishingiz mumkin;
            </div>
        </div>
    </div>
    <div style="page-break-after: always;"></div>
    """
    return cover_html



def generate_html_from_questions(data):
    full_html = """<html>
    <head>
      <meta charset="UTF-8">
      <style>
        body { font-family: Arial, sans-serif; margin: 10mm; }
        .category-title { font-weight: bold; font-size: 16px; margin-top: 20px; }
        .question { font-size: 14px; margin-top: 15px; }
        .options { margin-top: 5px; margin-bottom: 20px; margin-left: 10px; }
      </style>
    </head>
    <body>"""
    
    # Har bir list_item uchun:
    for list_item in data:
        list_id = list_item.get('list_id', "Noma'lum ID")
        questions = list_item.get('questions', [])
        grade = list_item.get('question_class', "Noma'lum")

        # 1. Bo'sh (qora) varaq – birinchi sahifa (to'liq bo'sh)
        full_html += '<div style="page-break-before: always; page-break-after: always;">&nbsp;</div>'
        
        # 2. Muqova varaq – maktab/test ma'lumotlari, ro'yxat raqami va kategoriya jadvali (yangi sahifa)
        full_html += '<div style="page-break-before: always;">'
        full_html += generate_cover_page_content(grade, list_id, questions)
        full_html += '</div>'
        
        # 3. Savollar bo'limi – yangi sahifadan boshlab, barcha savollar va variantlar ketma-ket chiqadi
        full_html += '<div style="page-break-before: always;">'
        # Savollarni kategoriya bo'yicha guruhlaymiz
        categories = defaultdict(list)
        for q in questions:
            key = (q.get('category', "Noma'lum"), q.get('subject', "Noma'lum"))
            categories[key].append(q)
        
        # Kategoriyalar bo'yicha ketma-ket chiqaramiz (har bir kategoriya uchun qo'shimcha sahifa ochilmaydi)
        for (category, subject), qs in categories.items():
            full_html += f"<div class='category-title'>{category.replace('_', ' ')} ({subject})</div>"
            for question in qs:
                order = question.get('order', '')
                cleaned_text = clean_html_and_remove_numbers(question.get('text', ''), order)
                full_html += f'<div class="question">{cleaned_text}</div>'
                options = question.get('options', [])
                if isinstance(options, list):
                    options_html = "<ul>" + "".join([f"<li>{opt}</li>" for opt in options]) + "</ul>"
                else:
                    options_html = str(options)
                full_html += f'<div class="options">{options_html}</div>'
        
        # Yakuniy page-break – keyingi list_item uchun
        full_html += '<div style="page-break-after: always;"></div>'
    
    full_html += "</body></html>"
    return full_html

def generate_pdf(html_content):
    options = {
        'page-size': 'A4',
        'encoding': 'UTF-8',
        'margin-top': '10mm',
        'margin-bottom': '10mm',
        'margin-right': '10mm',
        'margin-left': '10mm',
    }
    # wkhtmltopdf ning o'rnatilgan joyini moslashtiring:
    path_to_wkhtmltopdf = r"C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe"
    config = pdfkit.configuration(wkhtmltopdf=path_to_wkhtmltopdf)
    pdfkit.from_string(html_content, 'savollar_kitobchasi.pdf', options=options, configuration=config)

def get_desktop_path():
    user_system = platform.system()
    if user_system == "Windows":
        if os.path.exists(os.path.expanduser("~/Desktop")):
            return os.path.expanduser("~/Desktop")
        else:
            return os.path.join(os.path.expanduser("~"), "Рабочий стол")
    return os.path.expanduser("~/Desktop")

def select_and_save_pdf():
    questions_data = get_questions_from_api(api_url)
    if questions_data:
        html_content = generate_html_from_questions(questions_data)
        generate_pdf(html_content)
        root = tk.Tk()
        root.withdraw()  # Asosiy oynani yashiramiz
        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if file_path:
            os.rename("savollar_kitobchasi.pdf", file_path)
            print(f"PDF saqlandi: {file_path}")
        result = send_question_data_to_database_sync(questions_data)
        print(result)
        # 5. Savollarni o'chirish
        delete_questions_after_completion_sync()
    else:
        print("Savollarni olishda xatolik yuz berdi.")

def on_generate_pdf():
    select_and_save_pdf()

def on_exit():
    root.quit()

# GUI oynasini yaratish
root = tk.Tk()
root.title("Savollar Kitobi Generator")
root.geometry("400x200")  # Oyna o'lchami

generate_button = tk.Button(root, text="PDF Yaratish", width=20, height=2, bg="lightblue", fg="black", command=on_generate_pdf)
generate_button.pack(pady=20)

exit_button = tk.Button(root, text="Chiqish", width=20, height=2, bg="salmon", fg="white", command=on_exit)
exit_button.pack(pady=10)

root.mainloop()

if __name__ == "__main__":
    on_exit()
