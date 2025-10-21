import discord
from discord.ext import commands, tasks
import requests
import json
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
import os

# ============ CONFIGURATION ============
BOT_TOKEN = os.environ.get('BOT_TOKEN')  # Token depuis les variables d'environnement Render
INTERVALLE_VERIFICATION = 2  # Vérification toutes les 2 minutes

# Fichiers de sauvegarde
FICHIER_RECHERCHES = "recherches.json"
FICHIER_ANNONCES_VUES = "annonces_vues.json"

# ============ BOT DISCORD ============

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Variables globales
recherches = {}
annonces_vues = set()

# ============ GESTION DES DONNÉES ============

def charger_recherches():
    try:
        with open(FICHIER_RECHERCHES, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def sauvegarder_recherches(recherches):
    with open(FICHIER_RECHERCHES, 'w', encoding='utf-8') as f:
        json.dump(recherches, f, indent=2, ensure_ascii=False)

def charger_annonces_vues():
    try:
        with open(FICHIER_ANNONCES_VUES, 'r') as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def sauvegarder_annonces_vues(annonces_vues):
    with open(FICHIER_ANNONCES_VUES, 'w') as f:
        json.dump(list(annonces_vues), f)

# ============ FONCTIONS LEBONCOIN ============

def rechercher_annonces(url_recherche):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    try:
        session = requests.Session()
        response = session.get(url_recherche, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            scripts = soup.find_all('script')
            annonces = []
            
            for script in scripts:
                if script.string and '"list_id"' in script.string:
                    try:
                        json_start = script.string.find('"ads":[')
                        if json_start != -1:
                            json_part = script.string[json_start:]
                            bracket_count = 0
                            for i, char in enumerate(json_part):
                                if char == '[':
                                    bracket_count += 1
                                elif char == ']':
                                    bracket_count -= 1
                                    if bracket_count == 0:
                                        json_str = '{' + json_part[:i+1] + '}'
                                        data = json.loads(json_str)
                                        annonces = data.get('ads', [])
                                        break
                    except:
                        continue
            
            return annonces
        return []
    except Exception as e:
        print(f"Erreur recherche : {e}")
        return []

def extraire_prix(prix_data):
    if isinstance(prix_data, list) and len(prix_data) > 0:
        return prix_data[0]
    elif isinstance(prix_data, int):
        return prix_data
    return None

def calculer_temps_ecoule(date_str):
    """Calcule le temps écoulé depuis la publication"""
    try:
        from dateutil import parser
        date_pub = parser.parse(date_str)
        maintenant = datetime.now(date_pub.tzinfo)
        delta = maintenant - date_pub
        
        if delta.days > 0:
            return f"{delta.days} jour(s)"
        elif delta.seconds >= 3600:
            heures = delta.seconds // 3600
            return f"{heures} heure(s)"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute(s)"
        else:
            return "quelques secondes"
    except:
        return "récemment"

# ============ COMMANDES DU BOT ============

@bot.event
async def on_ready():
    global recherches, annonces_vues
    recherches = charger_recherches()
    annonces_vues = charger_annonces_vues()
    
    print(f'✅ Bot connecté en tant que {bot.user}')
    print(f'📋 {len(recherches)} recherche(s) chargée(s)')
    print(f'⏱️  Intervalle de vérification : {INTERVALLE_VERIFICATION} minute(s)')
    
    if not verifier_annonces.is_running():
        verifier_annonces.start()

@bot.event
async def on_command_error(ctx, error):
    """Gestion des erreurs"""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant ! Utilisez `!aide` pour voir comment utiliser cette commande.")
    else:
        print(f"Erreur : {error}")

@bot.command(name='aide')
async def aide(ctx):
    embed = discord.Embed(
        title="🤖 Guide du Bot Leboncoin",
        description="Surveillez automatiquement les annonces Leboncoin !",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📝 !ajouter <lien>",
        value="Ajoute une recherche à surveiller dans ce salon",
        inline=False
    )
    embed.add_field(
        name="🗑️ !supprimer <numéro>",
        value="Supprime une recherche de ce salon",
        inline=False
    )
    embed.add_field(
        name="📋 !liste",
        value="Liste toutes les recherches de ce salon",
        inline=False
    )
    embed.add_field(
        name="🔄 !verifier",
        value="Force une vérification immédiate",
        inline=False
    )
    embed.add_field(
        name="📊 !stats",
        value="Affiche les statistiques du bot",
        inline=False
    )
    
    embed.set_footer(text=f"💡 Vérification automatique toutes les {INTERVALLE_VERIFICATION} minute(s)")
    
    await ctx.send(embed=embed)

@bot.command(name='ajouter')
async def ajouter_recherche(ctx, url: str = None):
    if not url:
        await ctx.send("❌ Vous devez fournir un lien Leboncoin !\nExemple : `!ajouter https://www.leboncoin.fr/recherche?...`")
        return
    
    if not url.startswith("https://www.leboncoin.fr/recherche"):
        await ctx.send("❌ Le lien doit être un lien de recherche Leboncoin valide !")
        return
    
    channel_id = str(ctx.channel.id)
    
    if channel_id not in recherches:
        recherches[channel_id] = []
    
    for r in recherches[channel_id]:
        if r['url'] == url:
            await ctx.send("⚠️ Cette recherche existe déjà dans ce salon !")
            return
    
    recherches[channel_id].append({
        'url': url,
        'ajoutee_le': datetime.now().strftime('%d/%m/%Y %H:%M')
    })
    
    sauvegarder_recherches(recherches)
    
    embed = discord.Embed(
        title="✅ Recherche ajoutée !",
        description=f"Le bot surveillera cette recherche dans {ctx.channel.mention}",
        color=discord.Color.green()
    )
    embed.add_field(name="🔗 Lien", value=url[:100] + "...", inline=False)
    embed.add_field(name="📊 Total", value=f"{len(recherches[channel_id])} recherche(s) dans ce salon", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='supprimer')
async def supprimer_recherche(ctx, numero: int = None):
    channel_id = str(ctx.channel.id)
    
    if channel_id not in recherches or not recherches[channel_id]:
        await ctx.send("❌ Aucune recherche dans ce salon !")
        return
    
    if numero is None:
        await ctx.send("❌ Vous devez spécifier le numéro de la recherche !\nUtilisez `!liste` pour voir les numéros.")
        return
    
    if numero < 1 or numero > len(recherches[channel_id]):
        await ctx.send(f"❌ Numéro invalide ! Choisissez entre 1 et {len(recherches[channel_id])}")
        return
    
    recherches[channel_id].pop(numero - 1)
    
    if not recherches[channel_id]:
        del recherches[channel_id]
    
    sauvegarder_recherches(recherches)
    
    await ctx.send(f"✅ Recherche #{numero} supprimée !")

@bot.command(name='liste')
async def lister_recherches(ctx):
    channel_id = str(ctx.channel.id)
    
    if channel_id not in recherches or not recherches[channel_id]:
        await ctx.send("📋 Aucune recherche configurée dans ce salon.\nUtilisez `!ajouter <lien>` pour en ajouter une !")
        return
    
    embed = discord.Embed(
        title=f"📋 Recherches surveillées dans #{ctx.channel.name}",
        color=discord.Color.blue()
    )
    
    for i, recherche in enumerate(recherches[channel_id], 1):
        url = recherche['url']
        date = recherche['ajoutee_le']
        embed.add_field(
            name=f"#{i}",
            value=f"🔗 [{url[:50]}...]({url})\n📅 Ajoutée le {date}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='stats')
async def statistiques(ctx):
    total_recherches = sum(len(r) for r in recherches.values())
    total_salons = len(recherches)
    
    embed = discord.Embed(
        title="📊 Statistiques du Bot",
        color=discord.Color.gold()
    )
    embed.add_field(name="🔍 Recherches actives", value=total_recherches, inline=True)
    embed.add_field(name="📺 Salons surveillés", value=total_salons, inline=True)
    embed.add_field(name="👀 Annonces vues", value=len(annonces_vues), inline=True)
    embed.add_field(name="⏱️ Intervalle", value=f"{INTERVALLE_VERIFICATION} min", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='verifier')
async def verifier_manuellement(ctx):
    await ctx.send("🔄 Vérification en cours...")
    await verifier_toutes_recherches()
    await ctx.send("✅ Vérification terminée !")

# ============ TÂCHE AUTOMATIQUE ============

@tasks.loop(minutes=INTERVALLE_VERIFICATION)
async def verifier_annonces():
    await verifier_toutes_recherches()

async def verifier_toutes_recherches():
    global annonces_vues
    
    print(f"\n🔄 Vérification - {datetime.now().strftime('%H:%M:%S')}")
    
    for channel_id, recherches_salon in recherches.items():
        channel = bot.get_channel(int(channel_id))
        
        if not channel:
            continue
        
        for recherche in recherches_salon:
            url = recherche['url']
            annonces = rechercher_annonces(url)
            
            for annonce in annonces:
                id_annonce = str(annonce.get("list_id", ""))
                
                if not id_annonce or id_annonce in annonces_vues:
                    continue
                
                titre = annonce.get("subject", "")
                prix = extraire_prix(annonce.get("price"))
                url_annonce = annonce.get("url", "")
                
                if url_annonce and not url_annonce.startswith('http'):
                    url_annonce = f"https://www.leboncoin.fr{url_annonce}"
                
                location = annonce.get("location", {})
                ville = location.get("city_label", "") if isinstance(location, dict) else ""
                
                # Extraire plus d'informations
                images_data = annonce.get("images", {}).get("urls", [])
                attributes = annonce.get("attributes", [])
                body = annonce.get("body", "")
                
                # Créer un embed riche comme Lebondeal
                embed = discord.Embed(
                    title=f"🔥 {titre}",
                    url=url_annonce,
                    description=body[:300] + "..." if len(body) > 300 else body,
                    color=0xFF6B35,  # Couleur orange Leboncoin
                    timestamp=datetime.now()
                )
                
                # Champ Prix
                if prix:
                    embed.add_field(name="💰 Prix", value=f"**{prix} €**", inline=True)
                else:
                    embed.add_field(name="💰 Prix", value="Non spécifié", inline=True)
                
                # Champ Localisation
                if ville:
                    embed.add_field(name="📍 Emplacement", value=ville, inline=True)
                
                # Date de publication
                index_date = annonce.get("index_date", "")
                if index_date:
                    embed.add_field(name="🕐 Publié", value=f"il y a {calculer_temps_ecoule(index_date)}", inline=True)
                
                # Attributs du véhicule (année, km, etc.)
                infos_supplementaires = []
                for attr in attributes:
                    key = attr.get("key", "")
                    value = attr.get("value", "")
                    if key == "regdate":
                        infos_supplementaires.append(f"📅 Année: {value}")
                    elif key == "mileage":
                        infos_supplementaires.append(f"🚗 Kilométrage: {value} km")
                    elif key == "fuel":
                        infos_supplementaires.append(f"⛽ Carburant: {value}")
                
                if infos_supplementaires:
                    embed.add_field(name="ℹ️ Informations", value="\n".join(infos_supplementaires), inline=False)
                
                # Image principale en grand
                if images_data:
                    embed.set_image(url=images_data[0])
                
                # Miniatures des autres photos
                if len(images_data) > 1:
                    autres_photos = f"📸 {len(images_data)} photo(s) disponible(s)"
                    embed.add_field(name="Photos", value=autres_photos, inline=False)
                
                # Footer avec l'icône
                embed.set_footer(
                    text="Leboncoin • Cliquez sur le titre pour voir l'annonce complète",
                    icon_url="https://www.leboncoin.fr/favicon.ico"
                )
                
                try:
                    await channel.send(embed=embed)
                    annonces_vues.add(id_annonce)
                    print(f"✅ Nouvelle annonce envoyée dans #{channel.name}")
                except Exception as e:
                    print(f"❌ Erreur envoi : {e}")
    
    sauvegarder_annonces_vues(annonces_vues)

# ============ LANCEMENT ============

if __name__ == "__main__":
    if BOT_TOKEN:
        print("🚀 Démarrage du bot...")
        bot.run(BOT_TOKEN)
    else:
        print("⚠️ Token manquant ! Ajoutez la variable d'environnement BOT_TOKEN.")
