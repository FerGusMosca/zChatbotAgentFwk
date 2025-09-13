You are a binary classifier. 
Determine if the user wants to trigger the **portfolio rotation messaging intent**.

User input: {user_text}

Return JSON:
{
  "portfolio_rotation": true/false
}

Examples that should return true:
- "mandame los mensajes de rotacion de portfolio"
- "quiero enviar los mensajes de rotación a mis clientes"
- "rotación de portafolio"

Examples that should return false:
- "qué hora es"
- "contame un chiste"
