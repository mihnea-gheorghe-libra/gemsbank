import asyncio
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
import json
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    endpoint = os.getenv("AZURE_DOCINTEL_ENDPOINT")
    key = os.getenv("AZURE_DOCINTEL_KEY")
    client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (800, 400), color = (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((10,10), "ROMANIA CARTE DE IDENTITATE", fill=(0,0,0))
    d.text((10,50), "SERIA RK NR 123456", fill=(0,0,0))
    d.text((10,90), "CNP 1980101123452", fill=(0,0,0))
    d.text((10,130), "NUME POPESCU", fill=(0,0,0))
    d.text((10,170), "PRENUME ION", fill=(0,0,0))
    d.text((10,210), "VALABILITATE 01.01.20 - 01.01.2030", fill=(0,0,0))
    img.save("dummy_id.jpg")
    
    with open("dummy_id.jpg", "rb") as f:
        content = f.read()
        
    request = AnalyzeDocumentRequest(bytes_source=content)
    poller = client.begin_analyze_document("prebuilt-idDocument", request)
    result = poller.result()
    
    print("Documents:")
    for doc in result.documents:
        print(doc.fields.keys())
        for k, v in doc.fields.items():
            print(f"{k}: {v.value_string} / {v.value_date} (conf {v.confidence})")
            
    print("\nContent:")
    print(result.content)

main()
