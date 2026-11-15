"""Echo screens of 160/182/183 chars and a non-GSM-7 character to settle carrier-limit assumptions.

Run: python scripts/probe_at.py  (serves POST /probe on :8100); point an AT sandbox channel at it.
Reply text depends on the dialled `text` so each length can be observed in the simulator.
"""
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

app = FastAPI()


@app.post("/probe", response_class=PlainTextResponse)
async def probe(request: Request) -> str:
    form = await request.form()
    text = str(form.get("text", ""))
    mapping = {"": "CON Probe: 1=160 2=182 3=183 4=non-GSM-7", "1": 160, "2": 182, "3": 183}
    if text in ("1", "2", "3"):
        n = mapping[text]
        return "END " + "x" * (n - 4)
    if text == "4":
        return "END Probe é中€"
    return mapping[""]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=8100)
