
from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector
from datetime import time, timedelta
import re # Import regex for time format validation

app = Flask(__name__)
# Replace with a strong, unique key in production
# WARNING: Hardcoding secret key directly is not secure. Use environment variables.
app.secret_key = 'your_super_secret_and_random_key_replace_me'

# Database Connection Function
# !!! WARNING: Hardcoding credentials directly in code is not secure for production.
# Use environment variables or a configuration file instead.
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='root',
            password='Himanshu@778499',
            database='station_list'
        )
        return conn
    except mysql.connector.Error as err:
        # Log the error (in a real application)
        print(f"Database connection error: {err}")
        flash(f"Database connection error: Could not connect.", "danger")
        return None


# Helper function to format time value (timedelta, time object, or string) to HH:MM string
def format_time_to_hh_mm(time_value):
    if isinstance(time_value, (time, timedelta)):
         # Calculate total seconds. Handle timedelta specifically as it has days.
         total_seconds = (time_value.days * 86400 + time_value.seconds) if isinstance(time_value, timedelta) else (time_value.hour * 3600 + time_value.minute * 60 + time_value.second)
         hours = total_seconds // 3600
         minutes = (total_seconds % 3600) // 60
         # Format as HH:MM, ensuring two digits with zero padding
         return f'{hours:02d}:{minutes:02d}'
    elif isinstance(time_value, str) and len(time_value) >= 5:
        # If it's a string (e.g., 'HH:MM:SS' or 'HH:MM'), take the first 5 characters
        return time_value[:5]
    else:
        # Return empty string for None or unexpected types
        return ''

# Helper function for basic HH:MM time format validation
def is_valid_hh_mm(time_str):
    if not isinstance(time_str, str):
        return False
    # Regex to match HH:MM format (00-23 for hours, 00-59 for minutes)
    return re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_str) is not None

# ------------------------- OUTLET MENU ROUTE -------------------------
@app.route('/outlet_menu', methods=['GET', 'POST'])
def outlet_menu():
    # Get outlet_id from POST form data first (if available from a submission),
    # then from GET request args (for initial search or redirect).
    outlet_id = request.form.get('outlet_id') or request.args.get('outlet_id')

    menu_items_by_category = {}
    categories = []
    outlet_name = None # Default to None, will be fetched if outlet_id exists

    conn = get_db_connection()
    # If database connection failed, render template with limited info and flash message
    if conn is None:
        # Pass outlet_id back so the search input field can be pre-filled if user entered one
        return render_template('outlet_menu.html',
                               outlet_id=outlet_id,
                               outlet_name=outlet_name, # Will be None
                               categories=categories,  # Will be empty
                               menu_items_by_category=menu_items_by_category) # Will be empty


    cursor = conn.cursor(dictionary=True) # Use dictionary=True for column name access


    # --- Handle POST Requests (Form Submissions) ---
    if request.method == 'POST':
        # Ensure outlet_id is available from the form for any POST action
        if not outlet_id:
             flash("Outlet ID is missing in the form submission.", "danger")
             conn.close()
             return redirect(url_for('outlet_menu')) # Redirect back to the search page

        # --- Handle menu name update from the modal form ---
        if 'update_menu_name' in request.form:
            menu_id = request.form.get('menu_id')
            new_menu_name = request.form.get('menu_name')

            # Basic validation for required fields
            if menu_id and new_menu_name is not None and new_menu_name.strip():
                 try:
                     cursor.execute('''
                         UPDATE menu_items
                         SET menu_name = %s
                         WHERE menu_id = %s AND outlet_id = %s # Add outlet_id check for safety
                     ''', (new_menu_name.strip(), menu_id, outlet_id))
                     conn.commit()
                     # Check if any row was actually updated
                     if cursor.rowcount > 0:
                          flash(f"Menu item name (ID: {menu_id}) updated successfully!", "success")
                     else:
                          flash(f"Menu item ID {menu_id} not found for this outlet or no changes were made.", "warning")

                 except mysql.connector.Error as err:
                     conn.rollback()
                     flash(f"Error updating menu name: {err}", "danger")
                 except Exception as e:
                     conn.rollback()
                     flash(f"An unexpected error occurred during name update: {e}", "danger")
            else:
                 flash("Missing or invalid data for menu name update.", "danger")


        # --- Handle save changes to existing menu items from the main list form ---
        # Identified by the hidden input name="save_changes"
        elif 'save_changes' in request.form:
             updated_items_data = []
             validation_errors = [] # List to collect validation errors

             # Iterate through the submitted form data to find menu item updates
             # We will group fields by menu_id first
             items_form_data = {} # Dictionary to hold data for each menu_id

             for key, value in request.form.items():
                 # We are looking for keys like fieldname_menu_id (e.g., menu_name_10, description_10, cost_price_10)
                 # Use rsplit to handle keys like 'cost_price_10' or 'description_10' correctly
                 parts = key.rsplit('_', 1) # Split only on the last underscore

                 if len(parts) == 2:
                     field_name, menu_id = parts
                     # Ensure menu_id is numeric (basic check)
                     if menu_id.isdigit():
                         if menu_id not in items_form_data:
                             items_form_data[menu_id] = {'menu_id': menu_id}
                         # Store field value after stripping whitespace
                         items_form_data[menu_id][field_name] = value.strip()
                     # else: Ignore keys that don't match the expected format (like 'save_changes')


             # Now process the data collected for each item ID
             for menu_id, item_data in items_form_data.items():
                 # Ensure all expected fields are present for validation (use .get() with default)
                 # This handles cases where some fields might not be submitted for an item
                 full_item_data = {
                     'menu_id': item_data.get('menu_id', menu_id), # Use menu_id from key if not in data
                     'menu_name': item_data.get('menu_name', '').strip(),
                     'description': item_data.get('description', '').strip(),
                     'cost_price': item_data.get('cost_price'),
                     'selling_price': item_data.get('selling_price'),
                     'menu_otime': item_data.get('menu_otime'),
                     'menu_ctime': item_data.get('menu_ctime'),
                     'menu_status': item_data.get('menu_status'),
                     'menu_type': item_data.get('menu_type')
                 }

                 # --- Basic Server-Side Validation ---
                 is_valid = True
                 # Check if essential fields are missing for this item
                 # Note: description is optional
                 if not full_item_data['menu_name'] or \
                    full_item_data['cost_price'] is None or \
                    full_item_data['selling_price'] is None or \
                    full_item_data['menu_otime'] is None or \
                    full_item_data['menu_ctime'] is None or \
                    full_item_data['menu_status'] is None or \
                    full_item_data['menu_type'] is None:
                      validation_errors.append(f"Missing required data for item ID {menu_id}. Update skipped.")
                      is_valid = False
                 else: # Only perform format validation if required fields are present
                    try:
                        # Attempt to convert to float, will raise ValueError if not a valid number
                        float(full_item_data['cost_price'])
                    except (ValueError, TypeError):
                        validation_errors.append(f"Invalid cost price for item ID {menu_id}. Must be a number. Update skipped.")
                        is_valid = False
                    try:
                        float(full_item_data['selling_price'])
                    except (ValueError, TypeError):
                        validation_errors.append(f"Invalid selling price for item ID {menu_id}. Must be a number. Update skipped.")
                        is_valid = False
                    if not is_valid_hh_mm(full_item_data['menu_otime']):
                        validation_errors.append(f"Invalid opening time format (HH:MM) for item ID {menu_id}. Update skipped.")
                        is_valid = False
                    if not is_valid_hh_mm(full_item_data['menu_ctime']):
                        validation_errors.append(f"Invalid closing time format (HH:MM) for item ID {menu_id}. Update skipped.")
                        is_valid = False
                    # Add more specific status/type validation if needed

                 if is_valid:
                     updated_items_data.append(full_item_data)
                 # else: validation errors are collected, and the item is not added to updated_items_data


             # Flash all collected validation errors
             for error in validation_errors:
                 flash(error, "danger")

             if updated_items_data:
                 try:
                      # Execute updates for each item collected
                      # Ensure the number of %s matches the number of items in the tuple (10)
                      update_query = '''
                          UPDATE menu_items
                          SET menu_name = %s, description = %s, cost_price = %s, selling_price = %s, menu_otime = %s, menu_ctime = %s, menu_status = %s, menu_type = %s
                          WHERE menu_id = %s AND outlet_id = %s # Add outlet_id check for safety
                      '''
                      updated_count = 0
                      # Use a set to track IDs that were successfully updated for the success message
                      successfully_updated_ids = set()

                      for item in updated_items_data:
                           # Execute update only if the item passed validation and was added to updated_items_data
                           cursor.execute(update_query, (
                               item['menu_name'],
                               item['description'],
                               item['cost_price'],
                               item['selling_price'],
                               item['menu_otime'],
                               item['menu_ctime'],
                               item['menu_status'],
                               item['menu_type'],
                               item['menu_id'],
                               outlet_id # Use the outlet_id from the form
                           ))
                           # Sum up rows affected to count successful updates
                           if cursor.rowcount > 0:
                                updated_count += cursor.rowcount
                                successfully_updated_ids.add(item['menu_id'])


                      conn.commit()

                      if updated_count > 0:
                          # Construct a success message listing updated IDs if no validation errors
                          if not validation_errors:
                               # Convert set to list and then to string for display
                               updated_ids_str = ', '.join(map(str, sorted(list(successfully_updated_ids))))
                               flash(f"{updated_count} menu items updated successfully! (IDs: {updated_ids_str})", "success")
                          else:
                               # Show a partial success message if some items updated despite errors
                               flash(f"{updated_count} menu items updated successfully (some items skipped due to errors).", "warning")

                      # More specific messages for cases where no updates happened
                      elif not validation_errors and updated_count == 0 and items_form_data:
                           # If items were submitted, no validation errors, but no rows affected (e.g., no changes made)
                           flash("No changes were made to the submitted menu items.", "info")


                 except mysql.connector.Error as err:
                      conn.rollback()
                      flash(f"Error updating menu items: {err}", "danger")
                      print(f"Database error updating items: {err}") # Print error for debugging server-side
                 except Exception as e:
                      conn.rollback()
                      flash(f"An unexpected error occurred during saving changes: {e}", "danger")
                      print(f"Unexpected error saving changes: {e}") # Print error for debugging server-side
             elif not validation_errors and items_form_data:
                  # If items_form_data had items, but none passed validation
                  flash("No valid menu items submitted for saving changes (all items had validation errors).", "warning")
             elif not items_form_data:
                  # If no form data for items was found at all (e.g., form submitted without items)
                  flash("No menu item data received for saving changes.", "warning")


        # --- Handle add a new menu item form submission ---
        # Identified by the hidden input name="add_menu_item"
        elif 'add_menu_item' in request.form:
            menu_name = request.form.get('menu_name', '').strip()
            category_id = request.form.get('category_id')
            cost_price = request.form.get('cost_price')
            selling_price = request.form.get('selling_price')
            menu_otime = request.form.get('menu_otime')
            menu_ctime = request.form.get('menu_ctime')
            menu_type = request.form.get('menu_type')
            description = request.form.get('description', '').strip() # --- GET description ---

            # Define the default status for a new item
            menu_status = 'active' # <-- Define menu_status

            # Basic validation for required fields (description is optional) and format
            is_valid = True
            if not all([menu_name, category_id, cost_price, selling_price, menu_otime, menu_ctime, menu_type]):
                 flash("Missing data for adding new menu item. Please fill all required fields (Menu Name, Category, Prices, Times, Type).", "danger")
                 is_valid = False

            if is_valid: # Only proceed with format validation if required fields are present
                try:
                    float(cost_price)
                except (ValueError, TypeError):
                    flash("Invalid cost price for new item. Must be a number.", "danger")
                    is_valid = False
                try:
                    float(selling_price)
                except (ValueError, TypeError):
                    flash("Invalid selling price for new item. Must be a number.", "danger")
                    is_valid = False
                if not is_valid_hh_mm(menu_otime):
                    flash("Invalid opening time format (HH:MM) for new item.", "danger")
                    is_valid = False
                if not is_valid_hh_mm(menu_ctime):
                    flash("Invalid closing time format (HH:MM) for new item.", "danger")
                    is_valid = False
                # Add more specific status/type validation if needed

                # --- Check for duplicate item name within the same outlet and category ---
                if is_valid: # Only check for duplicates if basic validation passes
                    try:
                        cursor.execute(
                            "SELECT menu_id FROM menu_items WHERE outlet_id = %s AND category_id = %s AND menu_name = %s",
                            (outlet_id, category_id, menu_name)
                        )
                        if cursor.fetchone():
                            flash(f"Error adding menu item: An item named '{menu_name}' already exists in this category for this outlet.", "danger")
                            is_valid = False
                    except mysql.connector.Error as err:
                        flash(f"Database error during duplicate check: {err}", "danger")
                        is_valid = False # Prevent insertion if check fails
                    except Exception as e:
                        flash(f"An unexpected error occurred during duplicate check: {e}", "danger")
                        is_valid = False # Prevent insertion if check fails


            if is_valid: # Only attempt database insert if all validation passes
                 try:
                     # Ensure the number of %s matches the number of items in the tuple (10)
                     cursor.execute('''
                         INSERT INTO menu_items (outlet_id, category_id, menu_name, description, cost_price, selling_price, menu_otime, menu_ctime, menu_status, menu_type)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                     ''', (outlet_id, category_id, menu_name, description, cost_price, selling_price, menu_otime, menu_ctime, menu_status, menu_type)) # <-- Ensure 10 items in tuple
                     conn.commit()
                     flash(f"Menu item '{menu_name}' added successfully!", "success")
                 except mysql.connector.Error as err:
                     conn.rollback()
                     # Check for potential duplicate entry errors etc. - This might still catch database-level duplicates
                     if err.errno == 1062: # MySQL error code for duplicate entry
                          flash(f"Error adding menu item: Database reported a duplicate entry.", "danger") # More generic message now
                     else:
                          flash(f"Error adding menu item: {err}", "danger")
                          print(f"Database error adding item: {err}") # Print error for debugging server-side
                 except Exception as e:
                      conn.rollback()
                      flash(f"An unexpected error occurred during adding menu item: {e}", "danger")
                      print(f"Unexpected error adding item: {e}") # Print error for debugging server-side


        # --- Handle add a new category form submission ---
        # Identified by the hidden input name="add_category"
        elif 'add_category' in request.form:
            category_name = request.form.get('category_name', '').strip()

            # Basic validation
            if category_name:
                 try:
                      # --- Check if category already exists for this outlet ---
                      cursor.execute("SELECT category_id FROM menu_categories WHERE outlet_id = %s AND category_name = %s", (outlet_id, category_name))
                      if cursor.fetchone():
                           flash(f"Category '{category_name}' already exists for this outlet.", "warning")
                      else:
                           # --- If category does not exist, proceed with insertion ---
                           cursor.execute('''
                               INSERT INTO menu_categories (outlet_id, category_name)
                               VALUES (%s, %s)
                           ''', (outlet_id, category_name))
                           conn.commit()
                           flash(f"Category '{category_name}' added successfully!", "success")
                 except mysql.connector.Error as err:
                      conn.rollback()
                      flash(f"Error adding category: {err}", "danger")
                 except Exception as e:
                      conn.rollback()
                      flash(f"An unexpected error occurred during adding category: {e}", "danger")
            else:
                 flash("Category name is missing.", "danger")


        # --- Redirect after any POST action ---
        # Redirect back to the GET route for the same outlet_id to refresh the page with updated data
        # Use .get() with a default in case outlet_id was somehow lost
        conn.close() # Close connection before redirecting
        return redirect(url_for('outlet_menu', outlet_id=request.form.get('outlet_id', '')))


    # --- Handle GET Requests (Fetch and Display Data) ---
    # This block runs if the request method is GET
    if outlet_id:
        try:
            # Fetch outlet name
            cursor.execute("SELECT outlet_name FROM restaurants WHERE id = %s", (outlet_id,))
            result = cursor.fetchone()
            outlet_name = result['outlet_name'] if result else None

            # If outlet not found, flash a message
            if not outlet_name:
                 flash(f"No outlet found with ID {outlet_id}.", "warning")
                 # No need to proceed if outlet isn't found
                 conn.close()
                 return render_template('outlet_menu.html',
                                        outlet_id=outlet_id, # Pass ID back to pre-fill input
                                        outlet_name=None,
                                        categories=[],
                                        menu_items_by_category={})


            # Fetch categories for the found outlet
            cursor.execute("SELECT category_id, category_name FROM menu_categories WHERE outlet_id = %s ORDER BY category_name", (outlet_id,)) # Optional: order categories
            categories = cursor.fetchall()

            # Fetch menu items grouped by category
            if categories: # Only fetch items if categories exist for this outlet
                 for category in categories:
                      cursor.execute('''
                          SELECT menu_id, menu_name, description, cost_price, selling_price, menu_otime, menu_ctime, menu_status, menu_type
                          FROM menu_items
                          WHERE outlet_id = %s AND category_id = %s
                          ORDER BY menu_name # Optional: order items within category
                      ''', (outlet_id, category['category_id']))

                      # Process and format menu items before adding to the dictionary
                      items_list = []
                      for item in cursor.fetchall():
                           # Format menu_otime and menu_ctime to HH:MM for the HTML time input
                           item['menu_otime'] = format_time_to_hh_mm(item.get('menu_otime')) # Format opening time
                           item['menu_ctime'] = format_time_to_hh_mm(item.get('menu_ctime')) # Format closing time

                           # Description doesn't need formatting, just ensure it's not None if accessed
                           # The dictionary=True cursor handles NULLs, so .get('description') will return None or the string.
                           # HTML template handles None by not displaying. .strip() is applied on POST.

                           items_list.append(item) # Add processed item to the list

                      menu_items_by_category[category['category_name']] = items_list # Assign the list to the category

                 # Flash message if no items found but categories exist
                 # Check if any category actually had items
                 if not any(menu_items_by_category.values()):
                      flash(f"No menu items found for outlet '{outlet_name}' across its categories.", "info")

            else: # If no categories found for the outlet
                 flash(f"No categories found for outlet '{outlet_name}'. Add a category below.", "info")
                 # menu_items_by_category remains empty {}

        except mysql.connector.Error as err:
             flash(f"Error fetching data from the database: {err}", "danger")
             # Reset data on error to prevent displaying partial/incorrect info
             outlet_name = None
             categories = []
             menu_items_by_category = {}
             print(f"Database error fetching data: {err}") # Print error for debugging server-side
        except Exception as e:
             flash(f"An unexpected error occurred while fetching data: {e}", "danger")
             outlet_name = None
             categories = []
             menu_items_by_category = {}
             print(f"Unexpected error fetching data: {e}") # Print error for debugging server-side


    conn.close() # Close connection before rendering the template

    # Render the template with fetched (and formatted) data
    return render_template('outlet_menu.html',
                           outlet_id=outlet_id,
                           outlet_name=outlet_name,
                           categories=categories,
                           menu_items_by_category=menu_items_by_category)


# --- Run the Flask Development Server ---
if __name__ == '__main__':
    # Important: Before running, ensure your MySQL database 'station_list' exists
    # and contains the tables with the CORRECTED column names and types:
    # - 'restaurants' (with 'id' INT PRIMARY KEY, 'outlet_name' VARCHAR)
    # - 'menu_categories' (with 'category_id' INT PRIMARY KEY AUTO_INCREMENT, 'outlet_id' INT, 'category_name' VARCHAR)
    # - 'menu_items' (with ... 'description' TEXT, ... 'menu_otime' TIME NOT NULL, 'menu_ctime' TIME NOT NULL, ...)
    # Make sure the 'description' column exists as TEXT in your menu_items table.
    # Ensure you ran the SQL ALTER TABLE commands for renaming menu_timing and adding menu_ctime previously.

    app.run(debug=True) # Run in debug mode for development

