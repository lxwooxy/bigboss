import discord
from discord.ext import commands
import csv
import json
import time
from datetime import datetime
from tabulate import tabulate
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file
TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # Fetch the token

summary_message_id = None  # Stores the ID of the summary table message

# Intents setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.reactions = True

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

# File for persistent storage
TASKS_FILE = "tasks.json"

# Load tasks from file or initialize an empty dictionary
try:
    with open(TASKS_FILE, "r") as f:
        tasks = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    tasks = {}
    



@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")
    
    # Load tasks from the file
    load_tasks()

    # Fetch the summary channel
    summary_channel_name = "summary"
    summary_channel = discord.utils.get(bot.get_all_channels(), name=summary_channel_name)

    if summary_channel:
        print(f"Initializing summary channel: {summary_channel_name}")
        await clear_summary_channel(summary_channel)
    else:
        print(f"Summary channel '{summary_channel_name}' not found. Please create it.")




@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return  # Ignore bot reactions

    logs_channel_name = "logs"
    summary_channel_name = "summary"

    logs_channel = discord.utils.get(reaction.message.guild.channels, name=logs_channel_name)
    summary_channel = discord.utils.get(reaction.message.guild.channels, name=summary_channel_name)

    if not logs_channel or not summary_channel:
        await reaction.message.channel.send("Error: Logs or Summary channel not found.")
        return

    message_id = str(reaction.message.id)
    message_content = reaction.message.content

    # Add 🎉 (Confetti) to Complete a Task
    if reaction.emoji == "🎉":
        if message_id not in tasks:
            # If no 🫡 exists, create a new task and complete it immediately
            await reaction.message.add_reaction("🫡")
            tasks[message_id] = {
                "task": message_content,
                "start_time": time.time(),
                "end_time": time.time(),  # Instant completion
                "total_time": 0,
                "paused": False,
                "pause_time": None,
            }
            save_tasks()
            await logs_channel.send(f"Task '{message_content}' completed instantly (0 seconds).")
        else:
            # Complete an existing task
            task = tasks[message_id]
            if task.get("paused", False):
                # If the task is paused, unpause it
                pause_duration = time.time() - task["pause_time"]
                task["start_time"] += pause_duration
                task["paused"] = False
                task["pause_time"] = None

            # Mark the task as completed
            task["end_time"] = time.time()
            task["total_time"] = (task["end_time"] - task["start_time"]) / 60
            save_tasks()
            await reaction.message.remove_reaction("💀", bot.user)  # Remove 💀 if present
            await logs_channel.send(
                f"Task '{task['task']}' unpaused and marked as completed. Total time: {task['total_time']:.2f} minutes."
            )
        # Update the summary table
        await update_summary_table(summary_channel)

    # Add 💀 (Skull) to Pause a Task
    elif reaction.emoji == "💀":
        if message_id not in tasks:
            # If no 🫡 exists, create a new paused task
            await reaction.message.add_reaction("🫡")
            tasks[message_id] = {
                "task": message_content,
                "start_time": time.time(),
                "end_time": None,
                "total_time": None,
                "paused": True,
                "pause_time": time.time(),
            }
            save_tasks()
            await logs_channel.send(f"Task '{message_content}' started and paused immediately (0 seconds logged).")
        else:
            # Pause an existing task
            task = tasks[message_id]
            if not task.get("paused", False):
                task["paused"] = True
                task["pause_time"] = time.time()
                save_tasks()
                await logs_channel.send(f"Task '{task['task']}' has been paused.")
        # Update the summary table
        await update_summary_table(summary_channel)

    # Add 🫡 (Salute) to Start a Task
    elif reaction.emoji == "🫡":
        if message_id not in tasks:
            tasks[message_id] = {
                "task": message_content,
                "start_time": time.time(),
                "end_time": None,
                "total_time": None,
                "paused": False,
                "pause_time": None,
            }
            save_tasks()
            await logs_channel.send(f"Timer started for task: {message_content}")
        else:
            await logs_channel.send("Timer is already running for this task.")
        # Update the summary table
        await update_summary_table(summary_channel)


            
@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return  # Ignore bot reactions

    logs_channel_name = "logs"
    logs_channel = discord.utils.get(reaction.message.guild.channels, name=logs_channel_name)

    if not logs_channel:
        await reaction.message.channel.send("Error: Logs channel not found.")
        return

    message_id = reaction.message.id
    
    # Debug: Log the reaction event
    print(f"Reaction removed: {reaction.emoji} by {user}. Message ID: {message_id}")

    # Unpause task (💀)
    if reaction.emoji == "💀":
        if str(message_id) in tasks:
            task = tasks[str(message_id)]
            if task.get("paused", False):
                pause_duration = time.time() - task["pause_time"]
                task["paused"] = False
                task["pause_time"] = None
                task["start_time"] += pause_duration  # Adjust start time to account for pause
                save_tasks()
                await logs_channel.send(f"Task '{task['task']}' has been unpaused.")
            else:
                await logs_channel.send(f"Task '{task['task']}' is not currently paused.")
        else:
            await logs_channel.send("No task found to unpause.")


async def update_summary_table(channel):
    global summary_message_id
    print("Updating summary table (in progress tasks only)...")
    table_data = []
    for task_id, task in tasks.items():
        if task["end_time"] is None:  # Only include tasks that are in progress
            start_date, start_time = (
                datetime.fromtimestamp(task["start_time"]).strftime('%Y-%m-%d'),
                datetime.fromtimestamp(task["start_time"]).strftime('%H:%M:%S')
            ) if task["start_time"] else ("N/A", "N/A")
            total_time = f"{task['total_time']:.2f}" if task["total_time"] else "N/A"
            status = "Paused" if task.get("paused", False) else "Active"
            
            table_data.append([task["task"], start_date, start_time, total_time, status])

    headers = ["Task Description", "Start Date", "Start Time", "Total Time (mins)", "Status"]
    table = tabulate(table_data, headers, tablefmt="github")

    # Generate the table content
    content = f"```\nTask Summary (In Progress):\n\n{table}\n```"

    # Check if the summary message exists
    try:
        if summary_message_id:
            # Fetch the existing message
            summary_message = await channel.fetch_message(summary_message_id)
            await summary_message.edit(content=content)
            print("Summary table updated.")
        else:
            # Create a new summary message and store its ID
            new_message = await channel.send(content)
            summary_message_id = new_message.id
            print("New summary table created.")
    except discord.NotFound:
        # If the message doesn't exist, create a new one
        new_message = await channel.send(content)
        summary_message_id = new_message.id
        print("Summary table message not found. Created a new one.")



@bot.command()
async def export(ctx):
    filename = "tasks_summary.csv"
    with open(filename, "w", newline="") as csvfile:
        fieldnames = [
            "Task Description", 
            "Start Date", "Start Time", 
            "End Date", "End Time", 
            "Total Time (mins)"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for task_id, task in tasks.items():
            start_date, start_time = (
                datetime.fromtimestamp(task["start_time"]).strftime('%Y-%m-%d'),
                datetime.fromtimestamp(task["start_time"]).strftime('%H:%M:%S')
            ) if task["start_time"] else ("N/A", "N/A")
            end_date, end_time = (
                datetime.fromtimestamp(task["end_time"]).strftime('%Y-%m-%d'),
                datetime.fromtimestamp(task["end_time"]).strftime('%H:%M:%S')
            ) if task["end_time"] else ("In Progress", "In Progress")
            total_time = f"{task['total_time']:.2f}" if task["total_time"] else "N/A"

            writer.writerow({
                "Task Description": task["task"],
                "Start Date": start_date,
                "Start Time": start_time,
                "End Date": end_date,
                "End Time": end_time,
                "Total Time (mins)": total_time,
            })

    await ctx.send(file=discord.File(filename))
    
@bot.command()
async def delete_task(ctx, *, task_name: str):
    """Delete a task by its name."""
    # Search for the task by name
    task_to_delete = None
    task_id_to_delete = None
    for task_id, task in tasks.items():
        if task["task"].lower() == task_name.lower():  # Case-insensitive match
            task_to_delete = task
            task_id_to_delete = task_id
            break

    if task_to_delete:
        # Remove the task and save changes
        del tasks[task_id_to_delete]
        save_tasks()
        await ctx.send(f"Task '{task_name}' has been deleted.")
    else:
        # Task not found
        await ctx.send(f"No task found with the name: '{task_name}'")

async def clear_summary_channel(channel):
    """Clear all messages in the summary channel and create a new summary table."""
    global summary_message_id

    # Purge all messages in the channel
    await channel.purge()
    print(f"Cleared all messages in {channel.name}.")

    # Create a new summary table
    summary_message_id = None  # Reset the message ID
    await update_summary_table(channel)
    print("Created a new summary table.")



        
@bot.command()
async def clear(ctx, channel_name: str = None):
    """Clear all messages in a specified channel or the current channel."""
    # Define allowed channels
    allowed_channels = ["summary", "to-do", "logs"]

    # Determine which channel to clear
    target_channel = None
    if channel_name:
        # Search for the specified channel by name
        target_channel = discord.utils.get(ctx.guild.channels, name=channel_name)
        if not target_channel or target_channel.name not in allowed_channels:
            await ctx.send(f"Invalid channel. Allowed channels are: {', '.join(allowed_channels)}.")
            return
    else:
        # Default to the current channel
        target_channel = ctx.channel

    # Purge all messages in the target channel
    await target_channel.purge()
    print(f"Cleared all messages in {target_channel.name}.")

    # If clearing the summary channel, recreate the summary table
    if target_channel.name == "summary":
        global summary_message_id
        summary_message_id = None  # Reset the summary message ID
        await update_summary_table(target_channel)
        print("Recreated the summary table.")









def save_tasks():
    """Save the current tasks dictionary to a JSON file."""
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, indent=4)
        
def load_tasks():
    """Load tasks from a JSON file."""
    global tasks
    try:
        with open(TASKS_FILE, "r") as file:
            tasks = json.load(file)
            print("Tasks loaded from file.")
    except FileNotFoundError:
        tasks = {}  # Start with an empty dictionary if the file doesn't exist
        print("No tasks file found. Starting fresh.")


# Run the bot

bot.run(TOKEN)
