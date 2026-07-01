"""
ai_email.py — Helper to generate AI email drafts for prospecting.
"""

import json
import os
from typing import Dict, List, Optional
import ai_client

SYSTEM_PROMPT = """Eres un experto en ventas B2B para el sector minero chileno.
Tu objetivo es redactar un borrador de correo para prospectar a un contacto clave en una empresa mandante o minera.

Recibirás:
- Nombre del contacto y su rol.
- Empresa en la que trabaja.
- Lista de proyectos recientes o licitaciones de la empresa.

INSTRUCCIONES:
1. Redacta un asunto atractivo y directo.
2. Redacta un cuerpo de correo profesional, conciso y amigable.
3. Menciona sutilmente la actividad reciente de la empresa (proyectos) para demostrar conocimiento.
4. Deja marcadores como [Tu Nombre], [Tu Empresa] o [Tu Servicio] para que el usuario los complete.
5. El tono debe ser chileno profesional (no demasiado coloquial, pero directo).

RESPONDE SOLO con un JSON válido con esta estructura:
{
  "subject": "Asunto del correo...",
  "body": "Cuerpo del correo..."
}
"""

def generate_draft(contact_name: str, contact_role: str, company: str, recent_projects: List[Dict]) -> Dict[str, str]:
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "subject": f"Contacto - {company}",
            "body": f"Hola {contact_name},\n\nTe escribo por tu rol en {company}...\n\n(Configura OPENROUTER_API_KEY para usar IA)\n\nSaludos,"
        }
    
    projects_str = "\n".join([f"- {p.get('title', '')} (Fase: {p.get('phase', '')})" for p in recent_projects])
    
    prompt = f"""
Por favor redacta un correo para:
Nombre: {contact_name}
Rol: {contact_role or 'Desconocido'}
Empresa: {company}

Proyectos recientes de la empresa:
{projects_str or 'Sin proyectos recientes listados.'}
"""

    try:
        text = ai_client.call_llm(
            prompt=prompt,
            system=SYSTEM_PROMPT,
            max_tokens=500,
            model="claude-haiku-4-5-20251001"
        )
        
        # Parse JSON
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        
        data = json.loads(text)
        return {
            "subject": data.get("subject", ""),
            "body": data.get("body", "")
        }
    except Exception as e:
        return {
            "subject": f"Contacto - {company}",
            "body": f"Hola {contact_name},\n\n(Error al generar con IA: {str(e)})\n\nTe escribo por tu rol en {company}...\n\nSaludos,"
        }
