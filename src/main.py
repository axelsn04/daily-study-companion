from dotenv import load_dotenv
import os

from report import save_report
# from email_send import send_email  # descomenta si vas a enviar

def main():
    load_dotenv()

    path = save_report()
    print(f"Reporte generado: {path}")

    # Envío opcional
    # send_email(subject="Daily Study & News Companion", html_path=path)
    # print("Email enviado.")

if __name__ == "__main__":
    main()
