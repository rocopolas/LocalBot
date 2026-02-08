#!/usr/bin/env python3
import os
import sys
import chromadb
from chromadb.config import Settings
import logging

# Configure logging to show fewer details from libraries
logging.basicConfig(level=logging.ERROR)

def get_db_path():
    # Assuming script is in /scripts and data in /data
    # Determine the directory of the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up one level to the project root
    project_root = os.path.dirname(script_dir)
    # Construct path to data/chroma_db
    db_path = os.path.join(project_root, 'data', 'chroma_db')
    return db_path

def connect_db():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"Error: Database path not found at {db_path}")
        sys.exit(1)
    
    print(f"Connecting to database at: {db_path}")
    return chromadb.PersistentClient(path=db_path)

def list_collections(client):
    collections = client.list_collections()
    if not collections:
        print("No collections found.")
        return []
    
    print("\n--- Collections ---")
    for i, col in enumerate(collections):
        print(f"{i + 1}. {col.name}")
    return collections

def view_entries(collection):
    count = collection.count()
    print(f"\nTotal entries in '{collection.name}': {count}")
    
    if count == 0:
        return

    # Peek at the last 5 entries
    try:
        peek = collection.peek(limit=5)
        print(f"\nLast 5 entries:")
        
        ids = peek['ids']
        documents = peek.get('documents', [])
        metadatas = peek.get('metadatas', [])
        
        for i in range(len(ids)):
            print(f"\nID: {ids[i]}")
            if metadatas and i < len(metadatas):
                print(f"Metadata: {metadatas[i]}")
            if documents and i < len(documents):
                doc_text = documents[i] if documents[i] else "[No Content]"
                # Truncate document content for display
                doc_preview = doc_text[:100] + "..." if len(doc_text) > 100 else doc_text
                print(f"Content: {doc_preview}")
            print("-" * 40)
    except Exception as e:
        print(f"Error viewing entries: {e}")

def search_entries(collection):
    query = input("\nEnter search text (case-insensitive substring): ").strip()
    if not query:
        return

    print("Fetching all entries for text search (this might be slow for large DBs)...")
    try:
        # Get all data to perform manual filtering
        # Note: Ideally we'd use vector search, but we might not have the embedding function loaded here.
        all_data = collection.get()
        
        found_ids = []
        ids = all_data['ids']
        documents = all_data.get('documents', [])
        metadatas = all_data.get('metadatas', [])
        
        print(f"\n--- Search Results for '{query}' ---")
        
        count = 0
        for i in range(len(ids)):
            doc_text = documents[i] if documents and i < len(documents) and documents[i] else ""
            meta_text = str(metadatas[i]) if metadatas and i < len(metadatas) and metadatas[i] else ""
            
            if query.lower() in doc_text.lower() or query.lower() in meta_text.lower():
                count += 1
                found_ids.append(ids[i])
                print(f"\nMatch #{count}")
                print(f"ID: {ids[i]}")
                print(f"Metadata: {meta_text}")
                print(f"Content: {doc_text[:150]}...")
                print("-" * 40)
                
                if count >= 10:
                    print("Showing top 10 matches...")
                    break
        
        if count == 0:
            print("No matches found.")
            
    except Exception as e:
        print(f"Error searching: {e}")

def delete_entry(collection):
    entry_id = input("\nEnter ID to delete: ").strip()
    if not entry_id:
        print("Deletion cancelled.")
        return

    try:
        # Check if exists
        result = collection.get(ids=[entry_id])
        if not result['ids']:
            print(f"Error: Entry with ID '{entry_id}' not found.")
            return

        confirm = input(f"Are you sure you want to delete entry '{entry_id}'? (y/N): ").lower()
        if confirm == 'y':
            collection.delete(ids=[entry_id])
            print("Entry deleted successfully.")
        else:
            print("Deletion cancelled.")
    except Exception as e:
        print(f"Error deleting entry: {e}")

def wipe_collection(collection):
    print(f"\nWARNING: This will delete ALL data in '{collection.name}'.")
    confirm_name = input(f"Type collection name to confirm: ")
    
    if confirm_name == collection.name:
        try:
            # Delete all entries
            all_ids = collection.get()['ids']
            if all_ids:
                print(f"Deleting {len(all_ids)} entries...")
                collection.delete(ids=all_ids)
                print("Collection wiped successfully.")
            else:
                print("Collection is already empty.")
        except Exception as e:
            print(f"Error wiping collection: {e}")
    else:
        print("Confirmation failed. Aborted.")

def list_all_entries(collection):
    try:
        all_data = collection.get()
        ids = all_data['ids']
        if not ids:
             print("Collection is empty.")
             return

        print(f"\nTotal entries: {len(ids)}")
        for i, doc_id in enumerate(ids):
             print(f"{i+1}. {doc_id}")
             
    except Exception as e:
         print(f"Error listing all entries: {e}")

def main():
    try:
        client = connect_db()
    except Exception as e:
        print(f"Failed to connect to DB: {e}")
        return

    while True:
        try:
            print("\n" + "="*40)
            print("   LOCALBOT DB MANAGER   ")
            print("="*40)
            collections = list_collections(client)
            
            if not collections:
                # If no collections, verify path again or exit
                print("Database appears empty or locked.")
                retry = input("Retry? (y/n): ")
                if retry.lower() != 'y':
                    break
                continue

            print("\nSelect a collection to manage (or 'q' to quit):")
            choice = input("> ").strip()
            
            if choice.lower() == 'q':
                break
                
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(collections):
                    selected_col = collections[idx]
                else:
                    print("Invalid selection.")
                    continue
            except ValueError:
                print("Invalid input.")
                continue

            while True:
                print(f"\n--- Managing Collection: {selected_col.name} ---")
                print("1. View last 5 entries")
                print("2. Search entries (text match)")
                print("3. Delete entry by ID")
                print("4. Clear entire collection (DANGER)")
                print("5. List ALL IDs (can be long)")
                print("6. Back to collections")
                
                action = input("\nSelect action: ").strip()
                
                if action == '1':
                    view_entries(selected_col)
                elif action == '2':
                    search_entries(selected_col)
                elif action == '3':
                    delete_entry(selected_col)
                elif action == '4':
                    wipe_collection(selected_col)
                elif action == '5':
                    list_all_entries(selected_col)
                elif action == '6':
                    break
                else:
                    print("Invalid action.")
                    
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nAn error occurred in main loop: {e}")
            input("Press Enter to continue...")

if __name__ == "__main__":
    main()
