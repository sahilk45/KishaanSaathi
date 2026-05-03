import os
from typing import Annotated, List, TypedDict
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_groq import ChatGroq

from chatbot.tools import list_mandis, fetch_crop_price, get_weather, get_crop_advice

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    farmer_id: str

SYSTEM_INSTRUCTIONS = """You are KisanSaathi, a helpful agricultural assistant for Indian farmers.
Farmer ID: {farmer_id}

You have access to agricultural tools. You MUST use the native tool calling feature to use them.

══ PRICE FLOW ══
RULE: You MUST ALWAYS use the list_mandis tool BEFORE the fetch_crop_price tool. No exceptions.
Even if the farmer already mentions a mandi name — still use the list_mandis tool first.
CRITICAL: Always translate Hindi crop names to English before using the tool (e.g., Gehu -> Wheat, Chawal -> Rice).

STEP 1: Farmer mentions any crop.
        → Immediately use the list_mandis tool ONCE.
        → CRITICAL RULE: You MUST copy the entire numbered list of mandis from the tool's result and show it to the farmer in your message. Do NOT summarize or skip the list!
        → Ask: "Upar di gayi list mein se kaunsa number ya mandi naam chahiye?"
        → STOP and wait for farmer reply.

STEP 2: Farmer picks a mandi.
        → Use the fetch_crop_price tool ONCE. Show result. STOP.

══ WEATHER FLOW ══
If the farmer asks about the weather, rain, or heat, use the get_weather tool. STOP.

══ CROP ADVICE FLOW ══
If the farmer asks how to improve their score, yield, or get a loan, use the get_crop_advice tool.
The tool will return alternative options. Do NOT tell the farmer to do all options sequentially. Explain them as 'Aapke paas yeh vikalp (options) hain: Ya toh aap Option 1 kar sakte hain... ya phir Option 2 kar sakte hain'. Explain what to change and why. STOP.

══ CROP COMPARISON FLOW ══
If farmer asks "agar X ki jagah Y ugaau" or "X vs Y" or "Y try karun to kya hoga":
  → Use the get_crop_advice tool with mode="compare" and target_crop="Y".
  → target_crop should be the NEW crop farmer wants to try.

══ RULES ══
- Do NOT output XML or <function> tags. Use the standard JSON tool selector.
- Do NOT use parenthesis or underscores in your text when deciding to use a tool.
- Never use more than one tool per turn.
- Always respond in friendly Hinglish (Hindi + English mix).
- ERROR HANDLING: If a tool returns an error message (like DB Error, API Error, or Not Found), respond politely. Say something like: "Maafi chahunga kisan bhai, abhi kuch takneeki kharabi (technical issue) ke kaaran main yeh jaankari nahi la paa raha hoon. Kripya thodi der baad dobara koshish karein."
"""

llm_model = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
).bind_tools(
    [list_mandis, fetch_crop_price, get_weather, get_crop_advice],
    parallel_tool_calls=False,
    tool_choice="auto",
)

import re as _re
import json as _json
import uuid as _uuid

# Known int fields per tool — coerce strings to correct type before invoking
_TOOL_INT_FIELDS = {"get_weather": ["days"]}

def _recover_tool_call(exc) -> AIMessage | None:
    """
    When Groq returns 400 tool_use_failed, the model generated a malformed
    XML-style call like: <function=get_weather{"days": "1"}</function>
    We parse that string and synthesize a proper AIMessage with tool_calls
    so the graph can route to call_tool and run the tool normally.
    """
    err_str = str(exc)
    if "tool_use_failed" not in err_str:
        return None

    # Extract tool name and raw JSON args from failed_generation
    match = _re.search(r"<function=(\w+)(\{[^}]*\})", err_str)
    if not match:
        return None

    tool_name = match.group(1)
    try:
        raw_args = _json.loads(match.group(2))
    except Exception:
        raw_args = {}

    # Coerce known fields to correct types
    for field in _TOOL_INT_FIELDS.get(tool_name, []):
        if field in raw_args:
            try:
                raw_args[field] = int(raw_args[field])
            except (ValueError, TypeError):
                raw_args[field] = 3  # safe default

    tool_call_id = f"call_{_uuid.uuid4().hex[:12]}"
    return AIMessage(
        content="",
        tool_calls=[{
            "id": tool_call_id,
            "name": tool_name,
            "args": raw_args,
            "type": "tool_call",
        }],
    )

async def call_model(state: AgentState) -> dict:
    sys_msg = SystemMessage(content=SYSTEM_INSTRUCTIONS.format(farmer_id=state.get("farmer_id", "unknown")))
    messages = [sys_msg] + state["messages"]

    try:
        response = await llm_model.ainvoke(messages)
    except Exception as exc:
        recovered = _recover_tool_call(exc)
        if recovered is not None:
            # Recovered a valid tool_calls message — let the graph run the tool
            response = recovered
        else:
            raise

    return {"messages": [response]}

from langchain_core.runnables import RunnableConfig

async def call_tool(state: AgentState, config: RunnableConfig) -> dict:
    last_msg = state["messages"][-1]
    results  = []
    farmer_id = state.get("farmer_id", "")
    for tc in getattr(last_msg, 'tool_calls', []):
        name, args = tc["name"], dict(tc["args"])  # copy so we don't mutate
        if name == "get_weather" and "days" in args:
            args["days"] = int(args["days"])

        # We pass farmer_id via RunnableConfig AND directly as InjectedToolArg
        conf = {"configurable": {"farmer_id": farmer_id}}

        # Inject farmer_id directly for tools that use InjectedToolArg
        if name in ("get_weather", "get_crop_advice"):
            args["farmer_id"] = farmer_id

        if   name == "list_mandis":       res = await list_mandis.ainvoke(args, config=conf)
        elif name == "fetch_crop_price":  res = await fetch_crop_price.ainvoke(args, config=conf)
        elif name == "get_weather":       res = await get_weather.ainvoke(args, config=conf)
        elif name == "get_crop_advice":   res = await get_crop_advice.ainvoke(args, config=conf)
        else:                             res = f"❌ Unknown tool: {name}"
        results.append(ToolMessage(tool_call_id=tc["id"], content=str(res)))
    return {"messages": results}


def router(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, 'tool_calls', None):
        return "tools"
    return END

graph_builder = StateGraph(AgentState)
graph_builder.add_node("agent", call_model)
graph_builder.add_node("tools", call_tool)
graph_builder.set_entry_point("agent")
graph_builder.add_conditional_edges("agent", router, {"tools": "tools", END: END})
graph_builder.add_edge("tools", "agent")
agrisage_graph = graph_builder.compile()
