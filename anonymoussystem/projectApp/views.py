import base64
from django.shortcuts import render, get_object_or_404
from .models import UserEditor
from django.shortcuts import render
import os
import struct
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from Crypto.Cipher import AES
import spacy
import fitz  # PyMuPDF
import json
from .models import Messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
import os
from django.http import HttpResponse, JsonResponse, FileResponse
import re
import io 


# Alperenin yaptigi kisimlar //////////////////////

nlp = spacy.load("en_core_web_sm")

SECRET_KEY = b"This_is_a_32byte_key_for_AESshow"


def encrypt_text(text):
    cipher = AES.new(SECRET_KEY, AES.MODE_EAX)
    ciphertext, tag = cipher.encrypt_and_digest(text.encode("utf-8"))
    return base64.b64encode(cipher.nonce + tag + ciphertext).decode("utf-8")


def decrypt_text(encrypted_text):
    encrypted_data = base64.b64decode(encrypted_text)
    nonce, tag, ciphertext = encrypted_data[:16], encrypted_data[16:32], encrypted_data[32:]
    cipher = AES.new(SECRET_KEY, AES.MODE_EAX, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")


def anonymize_pdf(pdf_binary):
    pdf_document = fitz.open(stream=pdf_binary, filetype="pdf")
    replaced_texts = {}

    for page in pdf_document:
        text = page.get_text("text")
        doc = nlp(text)

        for ent in doc.ents:
            if ent.label_ == "PERSON":
                encrypted_name = encrypt_text(ent.text)
                replaced_texts[encrypted_name] = ent.text

                rects = page.search_for(ent.text)
                for rect in rects:
                    # Üzerine siyah bir dikdörtgen çiz
                    page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0))

    return pdf_document.write(), replaced_texts


def deanonymize_pdf(pdf_binary, replaced_texts):
    pdf_document = fitz.open(stream=pdf_binary, filetype="pdf")

    for page in pdf_document:
        text = page.get_text("text")

        for encrypted_name, original_name in replaced_texts.items():
            text = text.replace(f"[ANONYMIZED_{encrypted_name}]", original_name)

        page.insert_text((50, 50), text, fontsize=12)

    return pdf_document.write()



def admin(request):
    """Admin panelinde tüm makaleleri listele."""
    articles = UserEditor.objects.all()
    return render(request, 'admin.html', {'articles': articles})


def inspect_article(request, article_id):
    """Makale inceleme sayfasını aç ve PDF'yi göster."""
    article = get_object_or_404(UserEditor, id=article_id)
    pdf_url = f"/view_article/{article.id}/"
    return render(request, "inspectarticle.html", {"pdf_url": pdf_url, "article_id": article_id})


def view_article_pdf(request, article_id):
    """Veritabanındaki PDF'yi tarayıcıda aç."""
    article = get_object_or_404(UserEditor, id=article_id)

    if article.raw_article:
        return HttpResponse(article.raw_article, content_type="application/pdf", headers={
            "Content-Disposition": 'inline; filename="makale.pdf"'
        })

    return JsonResponse({"error": "PDF bulunamadı."}, status=404)


def deanonymize_article(request, article_id):
    article = get_object_or_404(UserEditor, id=article_id)

    if article.raw_article:
        anon_pdf, encrypted_data = anonymize_pdf(article.raw_article)  # Önce anonimleştir
        deanon_pdf = deanonymize_pdf(anon_pdf, encrypted_data)  # Sonra geri al

        # PDF'yi belleğe al
        pdf_buffer = io.BytesIO(deanon_pdf)

        # PDF'yi tarayıcıda açacak şekilde HTTP yanıtı döndür
        return FileResponse(pdf_buffer, content_type="application/pdf")

    return JsonResponse({"error": "PDF bulunamadı."}, status=404)


# Omerin yaptigi kisimlar /////////////////

def mainpage(request):
    return render(request, 'mainpage.html')

def referee(request):
    return render(request, 'referee.html')

def generate_tracking_number():
    """AES kullanarak 7 basamaklı benzersiz bir takip numarası üretir."""
    random_data = os.urandom(16)
    cipher = AES.new(os.urandom(16), AES.MODE_ECB)
    encrypted_data = cipher.encrypt(random_data)
    numeric_value = struct.unpack("Q", encrypted_data[:8])[0]
    return str(numeric_value % 9000000 + 1000000)

@csrf_exempt
def uploadarticle(request):
    """E-posta ve PDF dosyasını veritabanına kaydeder."""
    
    if request.method == 'GET':
        return render(request, 'uploadarticle.html')

    if request.method == 'POST':
        email = request.POST.get('email')
        pdf_file = request.FILES.get('file')

        if not email or not pdf_file:
            return JsonResponse({"error": "Lütfen e-posta adresinizi girin ve bir PDF yükleyin."}, status=400)

        tracking_number = generate_tracking_number()
        pdf_binary_data = pdf_file.read()

        user_article = UserEditor(
            tracking_no=tracking_number,
            owner_email=email,
            raw_article=pdf_binary_data
        )
        user_article.save()

        return JsonResponse({"success": "Makale başarıyla yüklendi.", "tracking_no": tracking_number})

    return JsonResponse({"error": "Geçersiz istek."}, status=400)


def queryarticle(request):
    return render(request, 'queryarticle.html')

@csrf_exempt
def send_message(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        email = data.get("email")
        message = data.get("message")

        if not email or not message:
            return JsonResponse({"error": "E-posta ve mesaj gereklidir."}, status=400)

        Messages.objects.create(sender=email, message=message)
        return JsonResponse({"success": "Mesaj başarıyla kaydedildi."})

    return JsonResponse({"error": "Geçersiz istek."}, status=400)


def get_messages(request):
    email = request.GET.get("email", "")
    
    if not email:
        return JsonResponse([], safe=False)

    # ID'ye göre sıralama yaparak en eski mesajlar önce gelsin
    messages = Messages.objects.filter(sender=email).order_by("id")  
    messages_list = [{"sender": msg.sender, "message": msg.message} for msg in messages]
    
    return JsonResponse(messages_list, safe=False)


def get_referee_documents(request):
    email = request.GET.get("email", "").strip()
    
    if not email:
        return JsonResponse([], safe=False)

    # Hakeme atanmış dokümanları filtrele
    documents = UserEditor.objects.filter(referee_email=email)
    documents_list = [
        {"id": doc.id, "owner_email": doc.owner_email, "pdf_path": doc.raw_article.name}
        for doc in documents
    ]
    
    return JsonResponse(documents_list, safe=False)
