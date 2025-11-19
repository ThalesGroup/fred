import asyncio
import httpx
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, List, Optional

class TravelState(TypedDict, total=False):
    user_query: str
    city: str
    category_tag: str
    lat: Optional[float]
    lon: Optional[float]
    pois: List[dict]
    poi_markdown: str

# Node 1: parser ville et catégorie simple
async def parse_city_and_category_node(state: TravelState, config):
    text = state.get("user_query","").lower()
    categories = ["restaurant","museum","hotel","cafe","bar","park"]
    category = "tourism"
    city = text
    for cat in categories:
        if cat in text:
            category = cat
            city = text.replace(cat,"").strip()
            break
    state["city"] = city.title()
    state["category_tag"] = category
    return state

# Node 2: chercher coordonnées ville
async def osm_search_node(state: TravelState, config):
    city = state.get("city")
    if not city:
        state["lat"] = state["lon"] = None
        return state
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city, "format":"json","limit":1}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)
        results = r.json()
        if results:
            state["lat"] = float(results[0]["lat"])
            state["lon"] = float(results[0]["lon"])
        else:
            state["lat"] = state["lon"] = None
    return state

# Node 3: fetch POIs minimal
async def fetch_pois_node(state: TravelState, config):
    lat = state.get("lat")
    lon = state.get("lon")
    cat = state.get("category_tag","tourism")
    if not lat or not lon:
        state["pois"] = []
        return state

    mapping = {
        "restaurant":("amenity","restaurant"),
        "cafe":("amenity","cafe"),
        "bar":("amenity","bar"),
        "hotel":("tourism","hotel"),
        "museum":("tourism","museum"),
        "park":("leisure","park"),
        "tourism":("tourism","attraction"),
    }
    key,value = mapping.get(cat,("tourism","attraction"))

    query=f"""
    [out:json][timeout:5];
    node(around:500,{lat},{lon})[{key}={value}];
    out 3;
    """
    url = "https://lz4.overpass-api.de/api/interpreter"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params={"data":query})
        data = r.json()
        state["pois"] = data.get("elements",[])
    return state

# Node 4: formatter Markdown
async def format_pois_node(state: TravelState, config):
    pois = state.get("pois",[])
    if not pois:
        state["poi_markdown"] = "*Aucun POI trouvé*"
        return state
    md = "| Nom | Lien OSM |\n| --- | --- |\n"
    for p in pois:
        name = p.get("tags",{}).get("name","-")
        osm_url = f"https://www.openstreetmap.org/node/{p.get('id','')}"
        md += f"| {name} | [OSM]({osm_url}) |\n"
    state["poi_markdown"] = md
    return state

# Main
async def main():
    builder = StateGraph(TravelState)
    builder.add_node("parse_city_and_category", parse_city_and_category_node)
    builder.add_node("osm_search", osm_search_node)
    builder.add_node("fetch_pois", fetch_pois_node)
    builder.add_node("format_pois", format_pois_node)

    builder.add_edge(START,"parse_city_and_category")
    builder.add_edge("parse_city_and_category","osm_search")
    builder.add_edge("osm_search","fetch_pois")
    builder.add_edge("fetch_pois","format_pois")
    builder.add_edge("format_pois",END)

    graph = builder.compile()

    user_input = input("Entrez votre texte (ex: restaurant lyon): ")
    initial_state = {"user_query": user_input}

    result = await graph.ainvoke(initial_state)
    print("\nRésultat Markdown:\n")
    print(result.get("poi_markdown","*Aucun résultat*"))

if __name__=="__main__":
    import asyncio
    asyncio.run(main())
    asyncio.run(main())
