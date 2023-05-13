"""Use mediawiki API to look up images on Wikimedia Commons."""

import urllib.parse

import requests

from . import utils

commons_start = "http://commons.wikimedia.org/wiki/Special:FilePath/"
commons_url = "https://www.wikidata.org/w/api.php"
page_size = 50


def commons_uri_to_filename(uri: str) -> str:
    """Given the URI for a file on commons return the filename of the file."""
    return urllib.parse.unquote(utils.drop_start(uri, commons_start))


def api_call(params: dict[str, str | int]) -> requests.models.Response:
    """Make an API call."""
    call_params = {
        "format": "json",
        "formatversion": 2,
        **params,
    }

    return requests.get(commons_url, params=call_params, timeout=5)


def image_detail(filenames, thumbheight=None, thumbwidth=None):
    """Detail for multiple images."""
    params = {
        "action": "query",
        "prop": "imageinfo",
        "iiprop": "url",
    }
    if thumbheight is not None:
        params["iiurlheight"] = thumbheight
    if thumbwidth is not None:
        params["iiurlwidth"] = thumbwidth

    images = {}

    for cur in utils.chunk(filenames, page_size):
        call_params = params.copy()
        call_params["titles"] = "|".join(f"File:{f}" for f in cur)

        r = api_call(call_params)

        for image in r.json()["query"]["pages"]:
            filename = utils.drop_start(image["title"], "File:")
            images[filename] = image["imageinfo"][0] if "imageinfo" in image else None

    return images
