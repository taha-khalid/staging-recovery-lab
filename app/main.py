import asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.db import engine

app = FastAPI()

def check_database_connection():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    
@app.get("/")
async def read_root():
    return {"message": "Welcome to the FastAPI application!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/ready")
async def ready_check():
    try:
        await asyncio.wait_for(
            asyncio.to_thread(check_database_connection),
            timeout=10,
        )
            
    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Database health check timed out",
        )
    
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database is unavailable",
        )   
    
    return {"status": "ready", "database": "connected"}
    
@app.post("/items", status_code=201)
def create_item(item: dict):
    if not isinstance(item.get("name"), str):
        raise HTTPException(
            status_code=422,
            detail="name must be a string",
        )

    try:
        with engine.begin() as connection:
            result = connection.execute(
                text("""
                    INSERT INTO items (name)
                    VALUES (:name)
                    RETURNING id, name, created_at
                """),
                {"name": item["name"]},
            )

            created_item = dict(result.mappings().one())

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to create item",
        )

    return {
        "message": "Item created successfully",
        "item": created_item,
    }

@app.get("/items")
def read_items():
    try: 
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                     SELECT name
                     FROM items
                     """)
            )
            items = [dict(row) for row in result.mappings().all()]
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch items",
        )
    return {"items": items}

@app.get("/items/{item_id}")
def read_item(item_id: int):
    try:
        with engine.connect() as connection:
            item = connection.execute(
                text("""
                     SELECT id, name, created_at
                     FROM items 
                     WHERE id = :item_id
                     """),
                {"item_id": item_id},
            ).mappings().first()
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch item: {str(e)}",
        )
    
    if item is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Item not found",
                    )

    return dict(item)