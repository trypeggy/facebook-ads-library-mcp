from fastmcp import FastMCP
from services.scrapecreators_service import get_platform_id, get_ads, get_scrapecreators_api_key


INSTRUCTIONS = """
This server is used to get currently running ads for a brand on Meta.
In order to get the running ads, you need to first get the Meta Platform ID for the brand, using the get_meta_platform_id tool.
Then, you can use the get_meta_ads tool to get the running ads for the brand.
"""


mcp_server = FastMCP(
   name="Meta Ads",
   instructions=INSTRUCTIONS
)


@mcp_server.tool(
  description="Given a company or brand name, return the Meta Platform ID for the brand.",
)
def get_meta_platform_id(brand_name: str) -> str:
    return get_platform_id(brand_name)


@mcp_server.tool(
  description="Given a Meta Platform ID, return the running ads for the brand.",
)
def get_meta_ads(platform_id: str) -> list[str]:
   ads = get_ads(platform_id)
   if len(ads) == 0:
      return "No current ads found."
   return ads


if __name__ == "__main__":
   get_scrapecreators_api_key()
   mcp_server.run(transport="stdio")
