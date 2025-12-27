# -*- coding: utf-8 -*-
"""
Module de gestion d'emails pour Cypher
Gère l'application locale Outlook (Lecture, Recherche, Envoi)
"""

from core.logger import get_logger

logger = get_logger("email_manager")


def email_manager(
    action: str, 
    recipient: str | None = None, 
    subject: str | None = None, 
    body: str | None = None, 
    query: str | None = None
) -> str:
    """
    Gère l'application locale Outlook (Lecture, Recherche, Envoi).
    Nécessite qu'Outlook soit installé et configuré sur le PC.
    """
    import win32com.client
    import pythoncom
    
    # Initialisation du contexte COM (nécessaire pour le multithreading)
    pythoncom.CoInitialize()

    try:
        # Connexion à Outlook
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        # 6 = Inbox (Boîte de réception)
        inbox = outlook.GetDefaultFolder(6)
    except Exception as e:
        return f"Erreur de connexion à Outlook. Est-il installé ? Erreur : {e}"

    action = action.lower()

    # --- LIRE LES NON-LUS ---
    if action == "read_recent":
        messages = inbox.Items
        messages.Sort("[ReceivedTime]", True)  # Plus récents d'abord
        
        unread_messages = []
        count = 0
        
        # On scanne les 50 derniers pour trouver les non-lus
        for message in messages:
            if count >= 5:
                break  # On s'arrête à 5 résumés
            try:
                if message.UnRead:
                    sender = message.SenderName
                    subj = message.Subject
                    # On nettoie un peu le corps
                    preview = message.Body[:100].replace('\r', ' ').replace('\n', ' ')
                    unread_messages.append(f"- De {sender} | Objet : {subj} | Aperçu : {preview}...")
                    count += 1
                if count >= 50:
                    break  # Sécurité pour ne pas scanner 10k mails
            except:
                continue
        
        if not unread_messages:
            return "Vous n'avez aucun nouvel e-mail non lu dans les 50 derniers reçus."
        
        return "Voici vos derniers e-mails non lus :\n" + "\n".join(unread_messages)

    # --- RECHERCHER ---
    if action == "search":
        if not query:
            return "Que dois-je chercher ?"
        
        messages = inbox.Items
        messages.Sort("[ReceivedTime]", True)
        
        found_messages = []
        count = 0
        
        # Recherche simple dans les 100 derniers mails
        for message in messages:
            try:
                if query.lower() in message.Subject.lower() or query.lower() in message.SenderName.lower():
                    found_messages.append(f"- [{message.ReceivedTime}] De {message.SenderName} : {message.Subject}")
                    count += 1
                if count >= 5:
                    break
                if count >= 100:
                    break
            except:
                continue
        
        if not found_messages:
            return f"Je n'ai rien trouvé pour '{query}' dans les 100 derniers e-mails."
        return f"Résultats pour '{query}' :\n" + "\n".join(found_messages)

    # --- ENVOYER ---
    if action == "send":
        if not recipient or not subject or not body:
            return "Pour envoyer un mail, il me faut : destinataire, objet et corps du message."
        
        try:
            # 0 = MailItem
            mail = win32com.client.Dispatch("Outlook.Application").CreateItem(0)
            mail.To = recipient
            mail.Subject = subject
            mail.Body = body
            mail.Send()
            return f"E-mail envoyé avec succès à {recipient}."
        except Exception as e:
            return f"Erreur lors de l'envoi : {e}"

    return "Action Outlook inconnue."

