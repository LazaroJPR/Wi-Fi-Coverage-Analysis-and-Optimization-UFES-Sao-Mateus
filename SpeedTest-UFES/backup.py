import gspread
from google.oauth2.service_account import Credentials
import csv

credentials_file = '/var/www/html/key.json'
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_file(credentials_file, scopes=scopes)

client = gspread.authorize(credentials)
spreadsheet = client.open("Teste de Velocidade")
worksheet = spreadsheet.worksheet("Dados")
worksheet.clear()

csv_file_path = '/var/www/html/results.csv'

with open(csv_file_path, mode='r') as file:
    csv_reader = csv.reader(file)
    csv_data = list(csv_reader)
    worksheet.update(csv_data)

print("Backup do arquivo CSV concluído com sucesso para o Google Sheets!")
