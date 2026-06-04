const MAX_TOKEN   = 'f9LHodD0cOKf3I_FDR-PuNxx_wY2cc3xcBwPsYmaaLOBGVqXJ1tWBFHTxxPZ5BXDSlqn6_mOoYcznxFrU2pu';
const MAX_CHAT_ID = '323409890';
const TG_TOKEN    = '8934552367:AAE2Gx5VFNONZ5D0OWdOLYjoGTj1JM1d1Gc';
const TG_CHAT_ID  = '994743403';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).end();

  const { text } = req.body || {};
  if (!text) return res.status(400).json({ error: 'no text' });

  await Promise.allSettled([
    fetch(`https://botapi.max.ru/messages?chat_id=${MAX_CHAT_ID}`, {
      method: 'POST',
      headers: {
        'Authorization': MAX_TOKEN,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ text })
    }),
    fetch(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: TG_CHAT_ID, text })
    })
  ]);

  return res.status(200).json({ ok: true });
}
