import unittest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as bot_app
from app import app, ask_gemini_pizzeria, load_data, save_data, DB_FILE

class TestViale50PizzeriaBot(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        # Pulisce dati di test
        save_data({"prenotazioni_tavoli": [], "ordini_domicilio": []})

    def tearDown(self):
        # Ripristina file pulito
        pass

    def test_01_orari_e_indirizzo(self):
        """Punto 1 dell'email: verifica che il bot conosca orari e indirizzo esatto."""
        reply = ask_gemini_pizzeria("test_user_orari", "Dove vi trovate esattamente e quali sono gli orari di apertura?")
        print("\n--- RISPOSTA ORARI/INDIRIZZO ---")
        print(reply)
        self.assertTrue(any(w in reply.lower() for w in ["resistenza", "50", "comiso"]))
        self.assertTrue(any(w in reply.lower() for w in ["19:30", "23:30", "lunedì", "chiuso"]))

    def test_02_impasti_disponibili(self):
        """Punto 2 dell'email: verifica che il bot conosca i 3 tipi di impasto."""
        reply = ask_gemini_pizzeria("test_user_impasti", "Quali tipi di impasto per la pizza avete?")
        print("\n--- RISPOSTA IMPASTI ---")
        print(reply)
        self.assertTrue(any(w in reply.lower() for w in ["classico", "tradizionale"]))
        self.assertTrue(any(w in reply.lower() for w in ["contemporaneo", "cornicione"]))
        self.assertTrue("integrale" in reply.lower())

    def test_03_prenotazione_tavolo_e_salvataggio_tablet(self):
        """Punto 3 dell'email: verifica che la prenotazione venga confermata e salvata per il tablet."""
        msg = "Vorrei prenotare un tavolo per 4 persone per sabato sera alle 21:00 a nome Francesco Battaglia"
        reply = ask_gemini_pizzeria("test_user_tavolo", msg)
        print("\n--- RISPOSTA PRENOTAZIONE TAVOLO ---")
        print(reply)
        
        # Verifica conferma nella risposta del bot
        self.assertTrue(any(w in reply.lower() for w in ["conferm", "prenotaz", "registrat", "riserv"]))
        
        # Verifica salvataggio nel database locale
        dati = load_data()
        self.assertGreaterEqual(len(dati["prenotazioni_tavoli"]), 1)
        ultima_prenotazione = dati["prenotazioni_tavoli"][-1]
        self.assertIn("Francesco Battaglia", ultima_prenotazione["dettagli"])

    def test_04_ordine_domicilio_e_salvataggio_tablet(self):
        """Punto 4 dell'email: verifica che l'ordine a domicilio con POS venga confermato e salvato per il tablet."""
        msg = "Vorrei ordinare a domicilio 2 pizze Viale 50 e 1 margherita in Via San Biagio 22 a Comiso per le 20:45, pago con POS"
        reply = ask_gemini_pizzeria("test_user_ordine", msg)
        print("\n--- RISPOSTA ORDINE DOMICILIO ---")
        print(reply)

        # Verifica conferma nella risposta del bot
        self.assertTrue(any(w in reply.lower() for w in ["ordin", "conferm", "registrat", "pos"]))

        # Verifica salvataggio nel database locale
        dati = load_data()
        self.assertGreaterEqual(len(dati["ordini_domicilio"]), 1)
        ultimo_ordine = dati["ordini_domicilio"][-1]
        self.assertIn("Via San Biagio 22", ultimo_ordine["dettagli"])

    def test_05_schermo_cassa_admin_html(self):
        """Verifica che la pagina /admin mostri sia il tavolo che l'ordine sul tablet della cassa."""
        # Popola con dati certi
        save_data({
            "prenotazioni_tavoli": [
                {"timestamp": "26/09/2026 20:00", "sender": "test_1", "dettagli": "Tavolo per 6 sabato 21:30 nome Luca", "conferma": "Confermato"}
            ],
            "ordini_domicilio": [
                {"timestamp": "26/09/2026 20:05", "sender": "test_2", "dettagli": "3 Margherite Via Roma 10 ore 20:30 POS", "conferma": "Registrato"}
            ]
        })
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Tavolo per 6", html)
        self.assertIn("3 Margherite Via Roma 10", html)
        self.assertIn("Pizzeria Viale50 - Schermo Cassa / Tablet", html)

if __name__ == "__main__":
    unittest.main()
