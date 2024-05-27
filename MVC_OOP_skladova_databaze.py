import sqlite3
import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import tkinter.font as tkFont
from datetime import datetime, timedelta
import os
import re
import sys
import unicodedata
import hashlib

class Model:
    """
    Třída Model se stará o práci s databází.
    """
    def __init__(self, db):
        """
        Inicializace modelu s připojením k databázi.
        
        :param db: Cesta k databázovému souboru.
        """
        self.conn = sqlite3.connect(db)
        self.cursor = self.conn.cursor()

    def fetch_col_names(self, table):
        """
        Načte názvy sloupců z dané tabulky.
        
        :param table: Název tabulky pro načtení názvů sloupců.
        :return: N-tice názvů sloupců.
        """
        query = f"SELECT * FROM {table} LIMIT 0"
        self.cursor.execute(query)
        return tuple(description[0] for description in self.cursor.description)


    def fetch_data(self, table):
        """
        Načte data z dané tabulky.
        
        :param table: Název tabulky pro načtení dat.
        :return: Všechna data z tabulky jako seznam n-tic.
        """
        query = f"SELECT * FROM {table}"
        self.cursor.execute(query)
        return self.cursor.fetchall()


    def fetch_sklad_data(self):
        """
        Načte rozšířená data z tabulky sklad včetně sloupce s informací, zda je množství pod minimem.
        
        :return: Data variant spolu s názvy dílů a dodavatelů.
        """
        query = """
        SELECT *,
               CASE 
                   WHEN Mnozstvi_ks_m_l < Min_Mnozstvi_ks THEN 1
                   ELSE 0
               END AS 'Pod_minimem' FROM sklad
        """
        self.cursor.execute(query)
        return self.cursor.fetchall()


    def fetch_varianty_data(self):
        """
        Načte rozšířená data variant, včetně názvů dílů a dodavatelů z ostatních tabulek a indikaci Pod minimem.
        
        :return: Data variant spolu s názvy dílů a dodavatelů a informací, zda je množství pod minimálním množstvím.
        """
        query = """
        SELECT v.*, s.Nazev_dilu, d.Dodavatel,
               CASE 
                   WHEN s.Mnozstvi_ks_m_l < s.Min_Mnozstvi_ks THEN 1
                   ELSE 0
               END AS 'Pod_minimem'
        FROM varianty v
        JOIN sklad s ON v.id_sklad = s.Evidencni_cislo
        JOIN dodavatele d ON v.id_dodavatele = d.id
        """
        self.cursor.execute(query)
        return self.cursor.fetchall()


    def fetch_item_variants(self, table, id_num, id_col_name):
        """
        Získání dat variant položky pro na základě ID pro zobrazení ve spodním frame.

        :param table: Název tabulky, ze které se položka získává.
        :param id_num: Číslo ID položky, ke které chceme získat varianty.
        :param id_col_name: Název sloupce, který obsahuje ID položky.
        :return: Seznam n-tic s daty variant položky a sloupcem Dodavatel z tabulky dodavatele
                 nebo None, pokud položka nebyla nalezena.
        """
        query = f"""
        SELECT v.*, d.Dodavatel
        FROM {table} AS v
        JOIN dodavatele AS d ON v.id_dodavatele = d.id
        WHERE v.{id_col_name} = ?
        """
        self.cursor.execute(query, (id_num,))
        return self.cursor.fetchall()



    def fetch_item_for_editing(self, table, id_num, id_col_name):
        """
        Získání dat položky pro účely editace na základě ID.
        
        :param table: Název tabulky, ze které se položka získává.
        :param id_num: Číslo ID položky, který chceme editovat.
        :param id_col_name: Název sloupce, který obsahuje ID položky.
        :return: Řádek s daty položky nebo None, pokud položka nebyla nalezena.
        """
        query = f"SELECT * FROM {table} WHERE {id_col_name} = ?"
        self.cursor.execute(query, (id_num,))
        return self.cursor.fetchone()


    def check_existence(self, id_sklad_value, id_dodavatele_value, current_table):
        """
        SQL dotaz pro ověření existence varianty před uložením nové.
        """
        query = f"""SELECT EXISTS(
                        SELECT 1 FROM {current_table} 
                        WHERE id_sklad = ? AND id_dodavatele = ?
                    )"""
        self.cursor.execute(query, (id_sklad_value, id_dodavatele_value))

        return self.cursor.fetchone()[0] == 1    


    def get_max_id(self, curr_table, id_col_name):
        """
        Vrátí nejvyšší hodnotu ID ze zadaného sloupce v zadané tabulce.

        :param curr_table: Název tabulky, ze které se má získat max ID.
        :param id_col_name: Název sloupce, ve kterém se hledá max ID.
        :return: Nejvyšší hodnota ID nebo None, pokud tabulka neobsahuje žádné záznamy.
        """
        query = f"SELECT MAX({id_col_name}) FROM {curr_table}"
        self.cursor.execute(query)
        max_id = self.cursor.fetchone()[0]
        return max_id if max_id is not None else 0


    def get_max_interne_cislo(self):
        """
        Získá nejvyšší hodnotu ve sloupci Interne_cislo z tabulky sklad.
        Pokud v tabulce nejsou žádné záznamy, vrátí se 0 jako výchozí hodnota.
        
        :Return int: Nejvyšší hodnota ve sloupci Interne_cislo nebo 0, pokud neexistují žádné záznamy.
        """
        self.cursor.execute("SELECT MAX(Interne_cislo) FROM sklad")
        max_value = self.cursor.fetchone()[0]
        return max_value if max_value is not None else 0


    def insert_item(self, table, columns, values):
        """
        Vloží novou položku do specifikované tabulky v databázi.

        :param table: Název tabulky, do které se má položka vložit.
        :param columns: Seznam sloupců, do kterých se vkládají hodnoty.
        :param values: Seznam hodnot odpovídajících sloupcům pro vkládání.
        """
        columns_str = ', '.join([f'"{col}"' for col in columns])
        placeholders = ', '.join('?' * len(columns))
        sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"
        self.cursor.execute(sql, values)
        self.conn.commit()


    def update_row(self, table, id_num, id_col_name, updated_values):
        """
        Aktualizuje řádek v zadané tabulce databáze na základě ID sloupce a jeho hodnoty.

        :param table: Název tabulky, ve které se má aktualizovat řádek.
        :param id_value: Hodnota ID, podle které se identifikuje řádek k aktualizaci.
        :param id_col_name: Název sloupce, který obsahuje ID pro identifikaci řádku.
        :param updated_values: Slovník, kde klíče jsou názvy sloupců a hodnoty
                               jsou aktualizované hodnoty pro tyto sloupce.
        """
        set_clause = ', '.join([f"`{key}` = ?" for key in updated_values.keys()])
        values = list(updated_values.values())
        values.append(id_num)
        sql = f"UPDATE `{table}` SET {set_clause} WHERE `{id_col_name}` = ?"

        self.cursor.execute(sql, values)
        self.conn.commit()


    def add_integer_column_with_default(self, new_col_name):
        """
        Přidá nový sloupec typu Integer do tabulky 'sklad' s výchozí hodnotou 0.
        
        :param new_col_name: Název nového sloupce, který má být přidán.
        """
        alter_table_query = f"ALTER TABLE sklad ADD COLUMN {new_col_name} INTEGER DEFAULT 0"
        self.cursor.execute(alter_table_query)
        self.conn.commit() 


    def delete_row(self, evidencni_cislo):
        """
        Smaže řádek ze skladu na základě jeho evidenčního čísla - ve sloupci Evidencni_cislo.      
        :Params evidencni_cislo (int): Evidencni_cislo řádku, který má být smazán.
        """
        self.cursor.execute("DELETE FROM sklad WHERE `Evidencni_cislo`=?", (evidencni_cislo,))
        self.conn.commit()


    def verify_user_credentials(self, username, password_hash):
        """
        Ověří, zda zadané uživatelské jméno a hash hesla odpovídají údajům v databázi.

        :param username: Uživatelské jméno k ověření.
        :param password_hash: Hash hesla k ověření.
        :return: True, pokud údaje odpovídají; jinak False.
        """
        query = "SELECT password_hash FROM uzivatele WHERE username = ?"
        self.cursor.execute(query, (username,))
        result = self.cursor.fetchone()
        if result:
            stored_password_hash = result[0]
            return stored_password_hash == password_hash
        else:
            return False        
        

    def get_user_info(self, username):
        """
        Získá jméno a roli uživatele z databáze na základě jeho uživatelského jména.

        Tato metoda vyhledá v databázi v tabulce "uzivatele" řádek, který odpovídá
        zadanému uživatelskému jménu, a vrátí jméno uživatele a jeho roli
        z odpovídajících sloupců "name" a "role".

        :param username: Uživatelské jméno, pro které má být informace získána.
        :return: Tuple obsahující jméno uživatele a jeho roli nebo (None, None),
                 pokud uživatel s takovým uživatelským jménem neexistuje.
        """
        try:
            self.cursor.execute("SELECT name, role FROM uzivatele WHERE username = ?", (username,))
            result = self.cursor.fetchone()
            if result:
                return result
            else:
                return (None, None)
        except Exception as e:
            messagebox.showerror("Chyba", f"Chyba při získávání informací o uživateli: {e}")
            return (None, None)



    def __del__(self):
        """
        Destruktor pro uzavření databázového připojení při zániku instance.
        """
        self.conn.close()



class View:
    """
    Třída View se stará o zobrazení uživatelského rozhraní.
    """
    table_config = {"sklad": {"check_columns": ('Pod_minimem', 'Ucetnictvi', 'Kriticky_dil',),
                              "hidden_columns": ('Pod_minimem', 'Ucetnictvi', 'Kriticky_dil', 'Objednano',),
                              "special_columns": ('Pod_minimem', 'Ucetnictvi', 'Kriticky_dil',),
                              "id_col_name": 'Evidencni_cislo',
                              "quantity_col": 7,
                              },
                    "audit_log": {"check_columns": ('Ucetnictvi',),
                                  "hidden_columns": ('Objednano', 'Poznamka', 'Cas_operace',),
                                  "special_columns": ('Ucetnictvi',),
                                  },
                    "varianty": {"check_columns": ('Pod_minimem',),
                                 "hidden_columns": ('Pod_minimem',),
                                 "special_columns": ('Pod_minimem',),                                  
                                 }
                    }
    

    def __init__(self, root, controller, current_table=None):
        """
        Inicializace GUI a nastavení hlavního okna.
        
        :param root(tk.Tk): Hlavní okno aplikace.
        :param controller(Controller): Instance kontroleru pro komunikaci mezi modelem a pohledem.
        """
        self.root = root
        self.controller = controller
        self.current_table = current_table
        self.sort_reverse = True
        self.item_frame_show = None         
        self.tab2hum = {'Ucetnictvi': 'Účetnictví', 'Kriticky_dil': 'Kritický díl', 'Evidencni_cislo': 'Evid. č.',
                        'Interne_cislo': 'Č. karty', 'Min_Mnozstvi_ks': 'Minimum', 'Objednano': 'Objednáno?',
                        'Nazev_dilu': 'Název dílu', 'Mnozstvi_ks_m_l': 'Akt. množství', 'Jednotky':'Jedn.',
                        'Umisteni': 'Umístění', 'Dodavatel': 'Dodavatel', 'Datum_nakupu': 'Datum nákupu',
                        'Cislo_objednavky': 'Objednávka', 'Jednotkova_cena_EUR': 'EUR/jednotka',
                        'Celkova_cena_EUR': 'Celkem EUR', 'Poznamka': 'Poznámka', 'Zmena_mnozstvi': 'Změna množství',
                        'Cas_operace': 'Čas operace', 'Operaci_provedl': 'Operaci provedl', 'Typ_operace': 'Typ operace',
                        'Datum_vydeje': 'Datum výdeje', 'Pouzite_zarizeni': 'Použité zařízení', 'id': 'ID',
                        'Kontakt': 'Kontaktní osoba', 'E-mail': 'E-mail', 'Telefon': 'Telefon',
                        'id_sklad': 'Evidenční číslo', 'id_dodavatele': 'ID dodavatele', 'Nazev_varianty': 'Název varianty',
                        'Cislo_varianty': 'Číslo varianty', 'Dodaci_lhuta': 'Dod. lhůta dnů',
                        'Min_obj_mnozstvi': 'Min. obj. množ.', 'Zarizeni': 'Zařízení', 'Nazev_zarizeni': 'Název zařízení',
                        'Umisteni': 'Umístění', 'Typ_zarizeni': 'Typ zařízení', 'Pod_minimem': 'Pod minimem'}
        self.suppliers_dict = self.controller.fetch_dict("dodavatele")
        self.suppliers = tuple(sorted(self.suppliers_dict.keys()))
        self.item_names_dict = self.controller.fetch_dict("sklad")
        self.item_names = tuple(sorted(self.item_names_dict.keys()))
        self.selected_option = "VŠE"
        self.selected_supplier = "VŠE"
        self.selected_item_name = "VŠE"
        self.start_date = None
        self.curr_table_config = View.table_config.get(self.current_table, {})
        if self.current_table == "sklad":
            devices = tuple(self.controller.fetch_dict("zarizeni").keys())
            self.curr_table_config['check_columns'] = self.curr_table_config['check_columns'] + devices
            self.curr_table_config['hidden_columns'] = self.curr_table_config['hidden_columns'] + devices
        self.mnozstvi_col = self.curr_table_config.get("quantity_col", [])
        self.check_columns = self.curr_table_config.get("check_columns", [])
        self.hidden_columns = self.curr_table_config.get("hidden_columns", [])
        self.special_columns = self.curr_table_config.get("special_columns", [])
        self.filter_columns = {col: tk.BooleanVar(value=False) for col in self.check_columns}
        self.id_col = 0
        self.click_col = 0
        self.id_col_name = self.curr_table_config.get("id_col_name", 'id')
        self.default_font = tkFont.nametofont("TkDefaultFont")
        self.custom_font = self.default_font.copy()
        self.custom_font.config(size=12, weight="bold")

        
    def customize_ui(self):
        """
        Přidání specifických menu a framů a labelů pro zobrazení informací o skladu.
        """
        self.initialize_menu()
        self.initialize_frames()
        self.initialize_searching()
        self.update_menu(self.spec_menus())
        self.update_context_menu()
        self.update_frames()
        self.initialize_check_buttons()
        self.initialize_treeview()
        self.initialize_bindings()
        self.additional_gui_elements()
        self.setup_columns(self.col_parameters())    


    def initialize_menu(self):
         """
         Inicializace hlavního společného menu.
         """
         self.menu_bar = tk.Menu(self.root)
         self.root.config(menu=self.menu_bar)

         common_menus = {
             "Soubor": [
                 (f"Export databáze {self.current_table} do csv", lambda: self.controller.export_csv(table=self.current_table)),
                 ("Export aktuálně vyfiltrovaných dat do csv", lambda: self.controller.export_csv(tree=self.tree)),
                 "separator",
                 ("Konec", self.root.destroy)
             ],
         }

         common_radiobutton_menus = {
             "Zobrazení": [
                 ("Sklad", 'sklad'),
                 ("Varianty", 'varianty'),
                 ("Auditovací log", 'audit_log'),
                 ("Dodavatelé", 'dodavatele'),
                 ("Zařízení", 'zarizeni'),
             ],
         }

         self.update_menu(common_menus)
         self.view_var = tk.StringVar()
         self.view_var.set(self.current_table)
         self.update_radiobuttons_menu(common_radiobutton_menus, self.view_var)


    def on_view_change(self):
         """
         Přepnutí pohledu na tabulku v menu pomocí radiobuttonů.
         """
         selected_view = self.view_var.get()
         self.controller.show_data(selected_view)


    def initialize_frames(self):
         """
         Inicializace společných framů, proběhne až v instanci dceřínné třídy.
         """
         self.frame = tk.Frame(self.root)
         self.frame.pack(fill=tk.BOTH, expand=True)
         self.top_frames_container = tk.Frame(self.frame)
         self.top_frames_container.pack(side=tk.TOP, fill=tk.X, expand=False)
         self.search_frame = tk.LabelFrame(self.top_frames_container, text="Vyhledávání",
                                           borderwidth=2, relief="groove")
         self.search_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
         self.filter_buttons_frame = tk.LabelFrame(self.top_frames_container, text="Filtrování dle výběru",
                                                   borderwidth=2, relief="groove")
         self.filter_buttons_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
         self.check_buttons_frame = tk.LabelFrame(self.frame, text="Filtrování dle zařízení",
                                                  borderwidth=2, relief="groove")
         self.check_buttons_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False)
         self.left_frames_container = tk.Frame(self.frame)
         self.left_frames_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)        


    def initialize_searching(self):
        """
        Inicializace políčka a tlačítka pro vyhledávání / filtrování.
        """
        self.search_entry = tk.Entry(self.search_frame, width=50)
        self.search_entry.pack(side=tk.LEFT, padx=2)
        self.search_entry.bind('<Return>', lambda _: self.controller.show_data(self.current_table))
        self.search_entry.bind("<Escape>", lambda _: self.search_entry.delete(0, tk.END))
        self.search_button = tk.Button(self.search_frame, text="Filtrovat",
                                       command=lambda: self.controller.show_data(self.current_table))
        self.search_button.pack(side=tk.LEFT, padx=5)


    def initialize_check_buttons(self):
        """
        Nastavení specifických checkbuttonů pro filtrování zobrazených položek.
        """         
        for col in self.filter_columns:
            if col in self.special_columns:
                checkbutton = tk.Checkbutton(self.filter_buttons_frame, text=self.tab2hum.get(col, col), variable=self.filter_columns[col],
                                             borderwidth=3, relief="groove", onvalue=True, offvalue=False, 
                                             command=lambda col=col: self.toggle_filter(col))
                checkbutton.pack(side='left', padx=5, pady=5)
            else:
                checkbutton = tk.Checkbutton(self.check_buttons_frame, text=self.tab2hum.get(col, col), variable=self.filter_columns[col],
                                             onvalue=True, offvalue=False, command=lambda col=col: self.toggle_filter(col))
                checkbutton.pack(side='left', pady=5)


    def initialize_treeview(self):
        """
        Inicializace TreeView a přidruženého scrollbaru.

        :param tree_frame: Frame pro zobrazení Treeview.
        """
        self.tree = ttk.Treeview(self.tree_frame, show='headings', height=30)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side=tk.RIGHT, fill="y")

        self.tree.tag_configure('evenrow', background='#FFFFFF')
        self.tree.tag_configure('oddrow', background='#F5F5F5')
        self.tree.tag_configure('low_stock', foreground='#CD5C5C')


    def initialize_bindings(self):
        """
        Vytvoření provázání na události.
        """
        self.tree.bind('<<TreeviewSelect>>', self.show_selected_item)  
        self.tree.bind('<Button-3>', self.on_right_click)


    def update_menu(self, additional_menus):
        """
        Aktualizuje hlavní menu aplikace přidáním nových položek menu,
        včetně oddělovačů mezi některými položkami.
        
        Parametry:
            additional_menus (dict): Slovník definující položky menu k přidání.
                                     Klíč slovníku je název menu a hodnota je seznam
                                     dvojic (název položky, příkaz) nebo řetězec 'separator'
                                     pro vložení oddělovače.
        """
        for menu_name, menu_items in additional_menus.items():
            new_menu = tk.Menu(self.menu_bar, tearoff=0)
            for item in menu_items:
                if item == "separator":
                    new_menu.add_separator()
                else:
                    item_name, command = item
                    new_menu.add_command(label=item_name, command=command)
            self.menu_bar.add_cascade(label=menu_name, menu=new_menu)
          

    def update_radiobuttons_menu(self, additional_radiobutton_menus, str_variable):
         """
         Aktualizuje hlavní menu aplikace přidáním nových radiobutton menu.

         Parametry:
             additional_radiobuttons_menus (dict): Slovník definující radiobuttony menu k přidání.
                                                   Klíč slovníku je název menu a hodnota je seznam
                                                   dvojic (název položky, tabulka).
         """
         for menu_name, menu_items in additional_radiobutton_menus.items():
             new_menu = tk.Menu(self.menu_bar, tearoff=0)
             for item in menu_items:
                 item_name, table = item
                 new_menu.add_radiobutton(label=item_name, variable=str_variable,
                                          value=table, command=self.on_view_change)
             self.menu_bar.add_cascade(label=menu_name, menu=new_menu)


    def update_context_menu(self):
         """
         Vytvoří kontextové menu aplikace při kliknutí pravým tlačítkem na položku v Treeview.
         """
         self.context_menu = tk.Menu(root, tearoff=0)
         self.context_menu.add_command(label="Uprav položku", command=self.edit_selected_item)


    def update_frames(self):
        """
        Aktualizuje specifické frame pro dané zobrazení.
        """
        self.item_frame = tk.LabelFrame(self.frame, width=435, text="Zobrazení detailu položky",
                                        borderwidth=2, relief="groove")
        self.item_frame.pack_propagate(False)
        self.item_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False)
        self.tree_frame = tk.LabelFrame(self.left_frames_container, text="Zobrazení vyfiltrovaných položek",
                                        borderwidth=2, relief="groove")
        self.tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)        


    def additional_gui_elements(self):
        """
        Vytvoření zbývajících specifických prvků gui dle typu zobrazovaných dat.
        """
        pass


    def setup_columns(self, col_params):
        """
        Nastavení sloupců pro TreeView.
        
        :col_params Seznam slovníků parametrů sloupců (width, minwidth, anchor, stretch...).
        """
        self.tree['columns'] = self.col_names
        for idx, col in enumerate(self.col_names):            
            self.tree.heading(col, text=self.tab2hum.get(col, col), command=lambda c=idx: self.on_column_click(c))
            self.tree.column(col, **col_params[idx])


    def on_combobox_change(self, event, attribute_name):
        """
        Aktualizuje příslušný atribut na základě vybrané hodnoty v comboboxu
        a filtruje zobrazovaná data podle aktuálních vybraných hodnot.
        """
        setattr(self, attribute_name, event.widget.get())
        self.controller.show_data(self.current_table)


    def delete_tree(self):
        """
        Vymaže všechny položky v Treeview.
        """
        for item in self.tree.get_children():
            self.tree.delete(item)


    def on_right_click(self, event):
        """
        Zobrazí kontextové menu po kliknutím pravým tlačítkem na položku v Treeview.
        """
        selected_item = self.select_item(warning_message="Není vybrána žádná položka k zobrazení.")
        if selected_item is None:
            return  
        x, y, _, _ = self.tree.bbox(selected_item)
        self.context_menu.post(event.x_root, event.y_root)            
   

    def add_data(self, current_data, current_id_num=None):
        """
        Vymazání všech dat v Treeview. Filtrace a třídění dle aktuálních hodnot parametrů.
        Vložení dat do TreeView. Změna hodnot v check_colums z 0/1 na NE/ANO pro zobrazení.
        Zvýraznění řádků pod minimem. Označení první položky v Treeview.
        Třídění podle zakliknuté hlavičky sloupce, při druhém kliknutí na stejný sloupec reverzně.

        :param current_data: aktuální data získaná z aktuální tabulky.
        :param current_id_num: id číslo aktuální položky k označení, pokud None, tak se označí první.        
        """          
        self.delete_tree()

        if self.current_table == "item_variants":
            sorted_data = current_data
        else:
            filtered_data = self.filter_data(current_data)
            sorted_data = sorted(filtered_data, key=self.sort_key, reverse=self.sort_reverse)
        
        treeview_item_ids = {}
        for idx, row in enumerate(sorted_data):      
            treeview_item_id = self.tree.insert('', tk.END, values=row)
            treeview_item_ids[row[0]] = treeview_item_id
            stripe_tag = 'evenrow' if idx % 2 == 0 else 'oddrow'
            if self.current_table == 'sklad' and int(row[7]) < int(row[4]):
                self.tree.item(treeview_item_id, tags=(stripe_tag, 'low_stock',))
            else: 
                self.tree.item(treeview_item_id, tags=(stripe_tag,))

        if current_id_num and current_id_num in treeview_item_ids:
            self.tree.selection_set(treeview_item_ids[current_id_num])
            self.tree.see(treeview_item_ids[current_id_num])
        else:
            self.mark_first_item() 
        

    def filter_data(self, data):
        """
        Vyfiltrování dat podle zadaných dat v search_entry ve všech tabulkách.
        V tabulce sklad navíc dle zaškrtnutých check buttonů a low stock filtru.
        V tabulce audit_log navíc dle comboboxu typ akce a v rozmezí datumů v date entry.
        V tabulce varianty dle comboboxu dodavatelé.

        :param data: Data pro filtraci dle search entry.
        :return: Přefiltrovaná data.
        """ 
        search_query = self.search_entry.get()
        if search_query:
            filtered_data = [row for row in data if search_query.lower() in " ".join(map(str, row)).lower()]
        else:
            filtered_data = data
    
        if self.current_table == "audit_log":
            if self.selected_option != "VŠE":
                filtered_data = [row for row in filtered_data if row[9] == self.selected_option]

        if self.current_table == "varianty":
            if self.selected_supplier != "VŠE":
                filtered_data = [row for row in filtered_data if row[-2] == self.selected_supplier]
            if self.selected_item_name != "VŠE":
                filtered_data = [row for row in filtered_data if row[-3] == self.selected_item_name]                

        if self.start_date:       
            filtered_data = [row for row in filtered_data if self.start_date <= (row[13] or row[14]) <= self.end_date]
            
        if any(value.get() for value in self.filter_columns.values()):          
            filtered_data_temp = []
            for row in filtered_data:
                include_row = True
                for col, is_filtered_var in self.filter_columns.items():
                    if is_filtered_var.get(): 
                        col_index = self.col_names.index(col)  
                        if row[col_index] != 1: 
                            include_row = False  
                            break
                if include_row:
                    filtered_data_temp.append(row)
            filtered_data = filtered_data_temp

        return filtered_data


    def toggle_filter(self, selected_col):
        """
        Metoda pro filtraci dat v tabulce podle zaškrtnutých check buttonů.
        Tato metoda umožňuje zaškrtnout nezávisle checkbuttony ve skupině 'special_group' 
        (Ucetnictvi, Kriticky_dil), zatímco pro ostatní checkbuttony (zařízení) zajišťuje,
        že aktivní může být maximálně jeden z nich. Při aktivaci jednoho z "normálních" 
        checkbuttonů jsou všechny ostatní "normální" checkbuttony odškrtnuty. Metoda aktualizuje 
        stav filtru pro daný sloupec a zobrazuje data podle nově aplikovaného filtru.

        :param selected_col: Název sloupce (check buttonu), který byl zaškrtnut nebo odškrtnut. 
                             Podle tohoto sloupce se určuje, který filtr bude aplikován nebo odstraněn.
        """
        status_of_chb = self.filter_columns[selected_col].get()

        if status_of_chb and selected_col not in self.special_columns:
            for col in self.filter_columns:
                if col not in self.special_columns and col != selected_col:
                    self.filter_columns[col].set(False)
                    
        self.controller.show_data(self.current_table)
            

    def on_column_click(self, clicked_col):
        """
        Metoda pro třídění dat v tabulce podle kliknutí na název sloupce.
        Přepnutí stavu třídění normální / reverzní a zobrazení přefiltrovaných dat.
        
        :param clicked_col: název sloupce, na který bylo kliknuto.
        """
        if clicked_col == self.click_col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.click_col = clicked_col
            self.sort_reverse = False
        self.controller.show_data(self.current_table, self.id_num)

        
    def sort_key(self, row):
        """
        Funkce sloužící jako klíč pro třídění dle sloupcu.
        Pokusí se převést hodnotu na float pro řazení číselných hodnot.
        Čísla mají přednost, takže pro ně vracíme (0, number).
        Textové hodnoty dostanou nižší prioritu, vracíme (1, value.lower()).

        :param row: porovnávaný řádek / položka v datatabázi.
        """
        value = row[self.click_col]
        try:
            number = float(value)
            return (0, number)
        except ValueError:
            return (1, value.lower())

        
    def mark_first_item(self):
        """
        Označení první položky v Treeview po načtení nových dat.
        """
        children = self.tree.get_children()
        if children:
            first_item = children[0]
            self.tree.selection_set(first_item)
            self.tree.focus(first_item)


    def widget_destroy(self):
        """
        Metoda na vymazání všechn dat z item_frame.
        """
        for widget in self.item_frame.winfo_children():
            widget.destroy()


    def select_item(self, warning_message="Žádná položka k zobrazení."):
        """
        Zkontroluje, zda je ve Treeview vybrána nějaká položka.
        
        :param warning_message: Zpráva, která se zobrazí v messageboxu, pokud není vybrána žádná položka.
        :return: Vrací ID vybrané položky v Treeview, nebo None, pokud žádná položka není vybrána.
        """
        try:
            selected_item = self.tree.selection()[0]
            self.id_num = int(self.tree.item(selected_item, 'values')[self.id_col])
            return selected_item
        except IndexError:
            messagebox.showwarning("Upozornění", warning_message)
            return None


    def show_selected_item(self, event=None):
        """
        Metoda pro vytvoření instance pro získání dat a zobrazení vybrané položky z treeview.
        """           
        if self.item_frame_show is None:
            self.widget_destroy()
            self.item_frame_show = ItemFrameShow(self.item_frame, self.controller, self.col_names,
                                                 self.tab2hum, self.current_table, self.check_columns)
            
        children = self.tree.get_children()
        if not children:
            messagebox.showwarning("Upozornění", "Nejsou žádné položky k zobrazení.")
            return

        selected_item = self.select_item(warning_message="Není vybrána žádná položka k zobrazení.")
        if selected_item is None:
            return  
       
        try:        
            item_values = self.tree.item(selected_item, 'values')
            self.item_frame_show.show_selected_item_details(item_values)
        except Exception as e:
            messagebox.showwarning("Upozornění", f"Při zobrazování došlo k chybě {e}.")
            return


    def edit_selected_item(self):
        """
        Metoda pro získání aktuálních dat z databáze pro vybranou položku a jejich zobrazení
        pro editaci.
        """
        selected_item = self.select_item()
        if selected_item is None:
            return       
        self.widget_destroy()    
        self.item_frame_show = None
        self.controller.show_data_for_editing(self.current_table, self.id_num, self.id_col_name,
                                                  self.item_frame, self.tab2hum, self.check_columns)


    def add_variant(self, curr_unit_price=None):
        """
        Metoda pro získání aktuálních dat z databáze pro vybranou položku a jejich zobrazení
        pro tvorbu nové varianty.
        """
        selected_item = self.select_item()
        if selected_item is None: return
        self.widget_destroy()
        self.item_frame_show = None
        varianty_table = "varianty"
        varianty_table_config = View.table_config.get(varianty_table, {})
        varianty_check_columns = varianty_table_config.get("check_columns", [])
        varianty_id_col_name = varianty_table_config.get("id_col_name", "id")
        self.controller.add_variant(self.current_table, self.id_num, self.id_col_name, self.item_frame,
                                    self.tab2hum, varianty_check_columns, varianty_table, varianty_id_col_name,
                                    curr_unit_price)
      
        
    def add_item(self):
        """
        Metoda pro přidání nové položky do aktuální tabulky.
        """
        self.widget_destroy()                      
        self.item_frame_show = None
        self.id_num = None
        self.controller.add_item(self.current_table, self.id_num, self.id_col_name,
                                     self.item_frame, self.tab2hum, self.check_columns)


    def hash_password(self, password):
        """
        Vypočítá a vrátí hash zadaného hesla pomocí algoritmu SHA-256.

        Tato funkce je určena pro bezpečné ukládání hesel v databázi. Místo uložení
        čitelného hesla se uloží jeho hash, což zvyšuje bezpečnost uchování hesel.

        :param password: Heslo, které má být zahashováno.
        :return: Zahashované heslo ve formátu hexadecimálního řetězce.
        """
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return password_hash


class LoginView(View):
    """
    Třída LoginView pro přihlášení uživatele. Dědí od třídy View.
    """
    def __init__(self, root, controller, col_names):
        """
        Inicializace specifického zobrazení pro dodavatele.
        
        :param root: Tkinter root widget, hlavní okno aplikace.
        :param controller: Instance třídy Controller.
        :param col_names: Seznam názvů sloupců (v tomto případě prázdný, protože se nepoužívá).
        """
        super().__init__(root, controller)
        self.additional_gui_elements()

    def place_window(self, window_width, window_height):
        """
        Metoda na umístění okna do středu obrazovky a stanovení velikosti okna dle zadaných parametrů.

        :params window_width, window_height - rozměry okna aplikace.
        """
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        center_x = int((screen_width/2) - (window_width/2))
        center_y = int((screen_height/2) - (window_height/2))

        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')


    def additional_gui_elements(self):
        """
        Vytvoření a umístění prvků GUI pro přihlašovací formulář.
        """
        self.place_window(410, 340)
        
        self.frame = tk.Frame(self.root, borderwidth=2, relief="groove")
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        login_label = tk.Label(self.frame , text="Přihlášení uživatele", font=("TkDefaultFont", 20))
        username_label = tk.Label(self.frame , text="Uživatelské jméno", font=("TkDefaultFont", 14))
        self.username_entry = tk.Entry(self.frame , font=("TkDefaultFont", 14))
        self.password_entry = tk.Entry(self.frame , show="*", font=("TkDefaultFont", 14))
        password_label = tk.Label(self.frame , text="Heslo", font=("TkDefaultFont", 14))
        login_button = tk.Button(self.frame , text="Login", bg='#333333', fg="#FFFFFF", borderwidth=2,
                                 relief="groove", font=("TkDefaultFont", 16), command=self.attempt_login)

        login_label.grid(row=0, column=0, columnspan=2, sticky="news", padx=5, pady=40)
        username_label.grid(row=1, column=0, padx=5)
        self.username_entry.grid(row=1, column=1, padx=5, pady=20)
        password_label.grid(row=2, column=0, padx=5)
        self.password_entry.grid(row=2, column=1, padx=5, pady=20)
        login_button.grid(row=3, column=0, columnspan=2, pady=30)

        self.username_entry.bind('<Return>', lambda _: self.attempt_login())
        self.password_entry.bind('<Return>', lambda _: self.attempt_login())

        self.username_entry.focus()


    def attempt_login(self):
        """
        Přihlášení uživatele do systému.
        """
        username = self.username_entry.get()
        password = self.password_entry.get()
        if not username or not password:
            messagebox.showinfo("Upozornění", "Nebylo zadáno uživatelské jméno nebo heslo")
            return

        password_hash = self.hash_password(password)

        self.controller.attempt_login(username, password_hash)

        
    def handle_failed_login(self):
        """
        Zobrazí dialogové okno s možností opakování přihlášení nebo ukončení aplikace
        po neúspěšném pokusu o přihlášení.
        """
        result = messagebox.askretrycancel("Přihlášení selhalo",
                                           "Nesprávné uživatelské jméno nebo heslo. Chcete to zkusit znovu?")
        if result:
            self.username_entry.delete(0, tk.END)
            self.password_entry.delete(0, tk.END)
            self.username_entry.focus()
        else:
            self.root.destroy()


    def start_main_window(self):
        """
        Metoda pro start tabulky sklad a vytvoření hlavního okna po úspěšném přihlášení.
        """        
        root.title('Skladová databáze HPM HEAT SK - verze 1.20 MVC OOP')
        
        if sys.platform.startswith('win'):
            root.state('zoomed')
        else:
            self.place_window(1920, 1080)
        
        self.controller.show_data("sklad")      
     

class SkladView(View):
    """
    Třída SkladView pro specifické zobrazení dat skladu. Dědí od třídy View.
    """
    def __init__(self, root, controller, col_names):
        """
        Inicializace specifického zobrazení pro sklad.
        
        :param root: Hlavní okno aplikace.
        :param controller: Instance třídy Controller pro komunikaci mezi modelem a pohledem.
        :param col_names: Názvy sloupců pro aktuální zobrazení.
        """
        super().__init__(root, controller, current_table = 'sklad')
        self.col_names = col_names
        self.customize_ui()


    def spec_menus(self):
        """
        Vytvoření slovníku pro specifická menu dle typu zobrazovaných dat.
        
        :return: Slovník parametrů menu k vytvoření specifických menu.
        """
        specialized_menus = {"Skladové položky": [("Přidat skladovou položku", self.add_item),
                                                  ("Upravit skladovou položku", self.edit_selected_item),
                                                  "separator",
                                                  ("Smazat skladovou položku", self.delete_row),],
                             "Příjem/Výdej": [("Příjem zboží", lambda: self.item_movements(action='prijem')),
                                              ("Výdej zboží", lambda: self.item_movements(action='vydej')),],
                             "Varianty": [("Přidat variantu", self.add_variant),],
                             }
        return specialized_menus


    def additional_gui_elements(self):
        """
        Vytvoření zbývajících specifických prvků gui dle typu zobrazovaných dat.
        """
        self.tree.bind('<<TreeviewSelect>>', self.show_item_and_variants)  
        
        self.item_variants_frame = tk.LabelFrame(self.left_frames_container, height=180,
                                                 text="Varianty", borderwidth=2, relief="groove")
        self.item_variants_frame.pack_propagate(False)
        self.item_variants_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False)        


    def col_parameters(self):
        """
        Nastavení specifických parametrů sloupců, jako jsou šířka a zarovnání.
        
        :return: Seznam slovníků parametrů sloupců k rozbalení.
        """
        col_params = []     
        for index, col in enumerate(self.col_names):
            match col:
                case 'Nazev_dilu':
                    col_params.append({"width": 400, "anchor": "w"})                
                case 'Dodavatel' | 'Poznamka':
                    col_params.append({"width": 150, "anchor": "w"})
                case 'Jednotky' | 'Evidencni_cislo' | 'Interne_cislo':
                    col_params.append({"width": 25, "anchor": "center"})
                case _ if col in self.hidden_columns:
                    col_params.append({"width": 0, "minwidth": 0, "stretch": tk.NO})
                case _:    
                    col_params.append({"width": 70, "anchor": "center"})
        return col_params


    def delete_row(self):
        """
        Vymaže označenou položku, pokud je to poslední zadaná položka a je nulový stav.
        """
        selected_item = self.select_item()
        if selected_item is None:
            return
        last_inserted_item = self.controller.get_max_id(self.current_table, self.id_col_name)
        mnozstvi = self.tree.item(self.selected_item)['values'][self.mnozstvi_col]
        if mnozstvi != 0 or self.id_num != last_inserted_item:
            messagebox.showwarning("Varování", "Lze smazat pouze poslední zadanou položku s nulovým množstvím!")
            return           
        response = messagebox.askyesno("Potvrzení mazání", "Opravdu chcete smazat vybraný řádek?")
        if response: 
            success = self.controller.delete_row(self.id_num)
            self.tree.delete(self.selected_item)
            self.mark_first_item()
            if success:
                messagebox.showinfo("Informace", "Vymazána poslední zadaná položka!")
            else:
                return
            
        self.controller.show_data(self.current_table)
        

    def item_movements(self, action):
        """
        Implementace funkcionality pro příjem a výdej zboží ve skladu.
        """
        selected_item = self.select_item()
        if selected_item is None: return
        self.widget_destroy()            
        self.item_frame_show = None
        self.controller.show_data_for_movements(self.current_table, self.id_num, self.id_col_name,
                                              self.item_frame, self.tab2hum, self.check_columns, action)


    def show_item_and_variants(self, event=None):
        """
        Metoda pro zobrazení označené položky z treeview v item frame a zobrazení variant
        vybrané položky v item_variants_frame.
        """
        self.show_selected_item()
        self.controller.show_item_variants(self.id_num, self.item_variants_frame)  

    
class AuditLogView(View):
    """
    Třída AuditLogView pro specifické zobrazení dat audit logu. Dědí od třídy View.
    """
    def __init__(self, root, controller, col_names):
        """
        Inicializace specifického zobrazení pro audit log.
        
        :param root: Hlavní okno aplikace.
        :param controller: Instance třídy Controller pro komunikaci mezi modelem a pohledem.
        :param col_names: Názvy sloupců pro aktuální zobrazení.
        """
        super().__init__(root, controller, current_table = 'audit_log')
        self.col_names = col_names   
        self.customize_ui()

        
    def spec_menus(self):
        """
        Vytvoření slovníku pro specifická menu dle typu zobrazovaných dat.
        
        :return: Slovník parametrů menu k vytvoření specifických menu.
        """
        specialized_menus = {}
        return specialized_menus


    def additional_gui_elements(self):
        """
        Vytvoření zbývajících specifických prvků gui dle typu zobrazovaných dat.
        """
        self.operation_label = tk.Label(self.filter_buttons_frame, text="Typ operace:")
        self.operation_label.pack(side=tk.LEFT, padx=5, pady=5)

        options = ["VŠE", "PŘÍJEM", "VÝDEJ"]
        self.operation_combobox = ttk.Combobox(self.filter_buttons_frame, values=options, state="readonly")
        self.operation_combobox.pack(side=tk.LEFT, padx=5, pady=5) 

        self.operation_combobox.set("VŠE")
        self.operation_combobox.bind("<<ComboboxSelected>>",
                                     lambda event, attr='selected_option': self.on_combobox_change(event, attr))

        self.month_entry_label = tk.Label(self.filter_buttons_frame, text="Výběr měsíce:")
        self.month_entry_label.pack(side=tk.LEFT, padx=5, pady=5)

        self.generate_months_list()
        self.month_entry_combobox = ttk.Combobox(self.filter_buttons_frame, width=12,
                                                 values=["VŠE"]+self.months_list, state="readonly")
        self.month_entry_combobox.pack(side=tk.LEFT, padx=5, pady=5)
        self.month_entry_combobox.set("VŠE")
        self.month_entry_combobox.bind("<<ComboboxSelected>>", self.on_combobox_date_change)


    def generate_months_list(self):
        """
        Generuje seznam měsíců od ledna 2024 do aktuálního měsíce a roku ve formátu MM-YYYY.
        Výsledkem je seznam řetězců, kde každý řetězec reprezentuje jeden měsíc v požadovaném formátu.
        Aktuální měsíc a rok je vypočítán z aktuálního systémového času a je také zahrnut ve výsledném seznamu.
        Seznam je vhodný pro použití v uživatelském rozhraní jako hodnoty pro výběrový seznam (např. Combobox),
        umožňující uživateli vybrat specifický měsíc a rok.
        """
        current_year = datetime.now().year
        current_month = datetime.now().month
        self.months_list = []

        for year in range(2024, current_year + 1):
            for month in range(1, 13):
                if year == current_year and month > current_month:
                    break
                self.months_list.append(f"{month:02d}-{year}")
        self.months_list.reverse() 


    def on_combobox_date_change(self, event):
        """
        Filtrování zobrazovaných dat v rozsahu počátečního a koncového datumu.
        """
        selected_month_year = self.month_entry_combobox.get()
        if selected_month_year == "VŠE":
            self.start_date=None
            self.end_date=None
        else:
            start_date = datetime.strptime(f"01-{selected_month_year}", "%d-%m-%Y")
            self.start_date = start_date.strftime('%Y-%m-%d')
            month, year = map(int, selected_month_year.split("-"))
            if month == 12:
                end_date = datetime(year, month, 31)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(days=1)
            self.end_date = end_date.strftime('%Y-%m-%d')

        self.controller.show_data(self.current_table)


    def col_parameters(self):
        """
        Nastavení specifických parametrů sloupců, jako jsou šířka a zarovnání.
        
        :return: Seznam slovníků parametrů sloupců k rozbalení.
        """
        col_params = []     
        for index, col in enumerate(self.col_names):
            match col:
                case 'Nazev_dilu':
                    col_params.append({"width": 230, "anchor": "w"})                
                case 'Dodavatel' | 'Pouzite_zarizeni':
                    col_params.append({"width": 100, "anchor": "w"})
                case 'Jednotky' | 'Evidencni_cislo' | 'Interne_cislo':
                    col_params.append({"width": 30, "anchor": "center"})
                case _ if col in self.hidden_columns:
                    col_params.append({"width": 0, "minwidth": 0, "stretch": tk.NO})
                case _:    
                    col_params.append({"width": 80, "anchor": "center"})
        return col_params


    def on_right_click(self, event):
        """
        Zobrazí kontextové menu po kliknutím pravým tlačítkem na položku v Treeview.
        """    
        pass

class DodavateleView(View):
    """
    Třída DodavateleView pro specifické zobrazení dat z tabulky dodavatele. Dědí od třídy View.
    """
    def __init__(self, root, controller, col_names):
        """
        Inicializace specifického zobrazení pro dodavatele.
        
        :param root: Hlavní okno aplikace.
        :param controller: Instance třídy Controller pro komunikaci mezi modelem a pohledem.
        :param col_names: Názvy sloupců pro aktuální zobrazení.
        """
        super().__init__(root, controller, current_table = 'dodavatele')
        self.col_names = col_names
        self.customize_ui()
        self.click_col = 1
        self.sort_reverse = False


    def spec_menus(self):
        """
        Vytvoření slovníku pro specifická menu dle typu zobrazovaných dat.
        
        :return: Slovník parametrů menu k vytvoření specifických menu.
        """
        specialized_menus = {
            "Dodavatelé": [
                ("Přidat dodavatele", self.add_item),
                ("Upravit dodavatele", self.edit_selected_item),
            ],
        }
        return specialized_menus


    def col_parameters(self):
        """
        Nastavení specifických parametrů sloupců, jako jsou šířka a zarovnání.
        
        :return: Seznam slovníků parametrů sloupců k rozbalení.
        """
        col_params = []     
        for index, col in enumerate(self.col_names):
            match col:          
                case 'Dodavatel':
                    col_params.append({"width": 300, "anchor": "w"})
                case _ if col in self.hidden_columns:
                    col_params.append({"width": 0, "minwidth": 0, "stretch": tk.NO})
                case _:    
                    col_params.append({"width": 80, "anchor": "center"})
        return col_params


class ZarizeniView(View):
    """
    Třída ZarizeniView pro specifické zobrazení dat z tabulky zarizeni. Dědí od třídy View.
    """
    def __init__(self, root, controller, col_names):
        """
        Inicializace specifického zobrazení pro dodavatele.
        
        :param root: Hlavní okno aplikace.
        :param controller: Instance třídy Controller pro komunikaci mezi modelem a pohledem.
        :param col_names: Názvy sloupců pro aktuální zobrazení.
        """
        super().__init__(root, controller, current_table = 'zarizeni')
        self.col_names = col_names
        self.customize_ui()
        self.sort_reverse = False


    def spec_menus(self):
        """
        Vytvoření slovníku pro specifická menu dle typu zobrazovaných dat.
        
        :return: Slovník parametrů menu k vytvoření specifických menu.
        """
        specialized_menus = {
            "Zařízení": [
                ("Přidat zařízení", self.add_item),
                ("Upravit zařízení", self.edit_selected_item),
            ],
        }
        return specialized_menus


    def col_parameters(self):
        """
        Nastavení specifických parametrů sloupců, jako jsou šířka a zarovnání.
        
        :return: Seznam slovníků parametrů sloupců k rozbalení.
        """
        col_params = []     
        for index, col in enumerate(self.col_names):
            match col:          
                case 'Nazev_zarizeni':
                    col_params.append({"width": 300, "anchor": "w"})
                case _ if col in self.hidden_columns:
                    col_params.append({"width": 0, "minwidth": 0, "stretch": tk.NO})
                case _:    
                    col_params.append({"width": 80, "anchor": "center"})
        return col_params


class VariantyView(View):
    """
    Třída VariantyView pro specifické zobrazení dat z tabulky varianty. Dědí od třídy View.
    """
    def __init__(self, root, controller, col_names):
        """
        Inicializace specifického zobrazení pro varianty.
        
        :param root: Hlavní okno aplikace.
        :param controller: Instance třídy Controller pro komunikaci mezi modelem a pohledem.
        :param col_names: Názvy sloupců pro aktuální zobrazení.
        """
        super().__init__(root, controller, current_table = 'varianty')
        self.col_names = col_names
        self.customize_ui()


    def additional_gui_elements(self):
        """
        Vytvoření zbývajících specifických prvků gui dle typu zobrazovaných dat.
        """   
        self.supplier_label = tk.Label(self.filter_buttons_frame, text="Dodavatel:")
        self.supplier_label.pack(side=tk.LEFT, padx=5, pady=5)

        options = ("VŠE",) + self.suppliers
        self.supplier_combobox = ttk.Combobox(self.filter_buttons_frame, values=options, state="readonly")
        self.supplier_combobox.pack(side=tk.LEFT, padx=5, pady=5) 

        self.supplier_combobox.set("VŠE")
        self.supplier_combobox.bind("<<ComboboxSelected>>",
                                     lambda event, attr='selected_supplier': self.on_combobox_change(event, attr))
        
        self.item_name_label = tk.Label(self.filter_buttons_frame, text="Skladová položka")
        self.item_name_label.pack(side=tk.LEFT, padx=5, pady=5)

        options = ("VŠE",) + self.item_names
        self.item_name_combobox = ttk.Combobox(self.filter_buttons_frame, values=options, width=50, state="readonly")
        self.item_name_combobox.pack(side=tk.LEFT, padx=5, pady=5) 

        self.item_name_combobox.set("VŠE")
        self.item_name_combobox.bind("<<ComboboxSelected>>",
                                     lambda event, attr='selected_item_name': self.on_combobox_change(event, attr))           


    def spec_menus(self):
        """
        Vytvoření slovníku pro specifická menu dle typu zobrazovaných dat.
        
        :return: Slovník parametrů menu k vytvoření specifických menu.
        """
        specialized_menus = {"Varianty": [("Upravit variantu", self.edit_selected_item),],}
        return specialized_menus


    def col_parameters(self):
        """
        Nastavení specifických parametrů sloupců, jako jsou šířka a zarovnání.
        
        :return: Seznam slovníků parametrů sloupců k rozbalení.
        """
        col_params = []     
        for index, col in enumerate(self.col_names):
            match col:          
                case 'Nazev_varianty':
                    col_params.append({"width": 300, "anchor": "w"})
                case "Nazev_dilu":
                    col_params.append({"width": 200, "anchor": "w", "stretch": tk.YES})
                case "Dodavatel":
                    col_params.append({"width": 100, "anchor": "w", "stretch": tk.YES})    
                case _ if col in self.hidden_columns:
                    col_params.append({"width": 0, "minwidth": 0, "stretch": tk.NO})
                case _:    
                    col_params.append({"width": 80, "anchor": "center"})
        return col_params


class ItemVariantsView(View):
    """
    Třída VariantyView pro specifické zobrazení dat z tabulky varianty. Dědí od třídy View.
    """
    def __init__(self, root, controller, col_names):
        """
        Inicializace specifického zobrazení pro varianty.
        
        :param root: Hlavní okno aplikace.
        :param controller: Instance třídy Controller pro komunikaci mezi modelem a pohledem.
        :param col_names: Názvy sloupců pro aktuální zobrazení.
        """
        super().__init__(root, controller, current_table = 'item_variants')
        self.col_names = col_names
        self.customize_ui()


    def customize_ui(self):
        """
        Přidání specifických menu a framů a labelů pro zobrazení informací o skladu.
        """
        self.initialize_frames()
        self.update_frames()
        self.initialize_treeview()
        self.setup_columns(self.col_parameters())


    def update_frames(self):
        """
        Aktualizuje specifické frame pro dané zobrazení.
        """
        self.tree_frame = tk.Frame(self.left_frames_container, borderwidth=2, relief="groove")
        self.tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)


    def col_parameters(self):
        """
        Nastavení specifických parametrů sloupců, jako jsou šířka a zarovnání.
        
        :return: Seznam slovníků parametrů sloupců k rozbalení.
        """
        col_params = []     
        for index, col in enumerate(self.col_names):
            match col:          
                case 'Nazev_varianty':
                    col_params.append({"width": 300, "anchor": "w"})
                case "Nazev_dilu":
                    col_params.append({"width": 200, "anchor": "w", "stretch": tk.YES})
                case "Dodavatel":
                    col_params.append({"width": 100, "anchor": "w", "stretch": tk.YES})  
                case _ if col in self.hidden_columns:
                    col_params.append({"width": 0, "minwidth": 0, "stretch": tk.NO})
                case _:    
                    col_params.append({"width": 80, "anchor": "center"})
        return col_params
            

    def on_column_click(self, clicked_col):
        """
        Metoda pro třídění dat v tabulce podle kliknutí na název sloupce.
        Pro zobrazení variant skladových položek je třídění zrušeno.
        
        :param clicked_col: název sloupce, na který bylo kliknuto.
        """
        pass
            

class ItemFrameBase:
    """
    Třída ItemFrameBase je rodičovská třída pro práci s vybranými položkami.
    """
    table_config = {
        "sklad": {"order_of_name": 6, "id_col_name": "Evidencni_cislo", "quantity_col": 7,
                  "unit_price_col": 13, "focus": 'Nazev_dilu', "name": "SKLADOVÉ KARTY",},
        "audit_log": {"order_of_name": 5, "name": "POHYBU NA SKLADĚ",},
        "dodavatele": {"order_of_name": 1, "focus": 'Dodavatel', "name": "DODAVATELE",},
        "varianty": {"order_of_name": 3, "focus": 'Nazev_varianty', "name": "VARIANTY",},
        "zarizeni": {"order_of_name": 1, "focus": 'Zarizeni', "name": "ZAŘÍZENÍ",},
        }

    def __init__(self, master, controller, col_names, tab2hum, current_table, check_columns):
        """
        Inicializace prvků v item_frame.
        
        :param master: Hlavní frame item_frame, kde se zobrazují informace o položkách.
        :param tree: Treeview, ve kterém se vybere zobrazovaná položka.
        :param col_names: Názvy sloupců zobrazované položky.
        :param dict_tab2hum: Slovník s převodem databázových názvů sloupců na lidské názvy.
        :param current_table: Aktuálně otevřená tabulka databáze.
        """
        self.master = master
        self.controller = controller
        self.col_names = col_names
        self.tab2hum = tab2hum
        self.current_table = current_table
        self.check_columns = check_columns
        self.suppliers_dict = self.controller.fetch_dict("dodavatele")
        self.suppliers = tuple(sorted(self.suppliers_dict.keys()))
        self.current_user = self.controller.current_user
        self.name_of_user = self.controller.name_of_user
        self.unit_tuple = ("ks", "kg", "pár", "l", "m", "balení")
        self.curr_table_config = ItemFrameBase.table_config[self.current_table]
        self.special_columns = ('Ucetnictvi', 'Kriticky_dil', 'Pod_minimem')

        self.initialize_fonts()
        self.initialize_frames()


    def initialize_fonts(self):
        """
        Inicializace používaných fontů.
        """ 
        self.default_font = tkFont.nametofont("TkDefaultFont")
        self.custom_font = self.default_font.copy()
        self.custom_font.config(size=12, weight="bold")
        

    def initialize_frames(self):
        """
        Vytvoření framů ve frame item_frame.
        """
        self.title_frame = tk.Frame(self.master, bg="yellow", borderwidth=2, relief="groove")
        self.title_frame.pack(side=tk.TOP,fill=tk.X, padx=2, pady=2)   
        self.show_frame = tk.Frame(self.master, borderwidth=2, relief="groove")
        self.show_frame.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)


    def update_frames(self, action):
        """
        Vytvoření a nastavení dalších framů v show_frame pro aktuální zobrazení.

        :param action: Typ akce pro tlačítko uložit - add pro přidání nebo edit pro úpravu, None - žádné.
        """
        self.top_frame = tk.Frame(self.show_frame, borderwidth=2, relief="groove")
        self.top_frame.pack(side=tk.TOP, fill=tk.X)     
        self.left_frame = tk.Frame(self.top_frame, borderwidth=2, relief="groove")
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.right_common_frame = tk.Frame(self.top_frame, borderwidth=2, relief="groove")
        self.right_common_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=2, pady=2)
        self.right_top_frame = tk.Frame(self.right_common_frame, borderwidth=2, relief="groove")
        self.right_top_frame.pack(side=tk.TOP, fill=tk.BOTH, padx=2, pady=2)        
        self.right_frame = tk.Frame(self.right_common_frame, borderwidth=2, relief="groove")
        self.right_frame.pack(side=tk.TOP, fill=tk.BOTH, padx=2, pady=2)

        if action:        
            self.bottom_frame = tk.Frame(self.show_frame)
            self.bottom_frame.pack(side=tk.BOTTOM, pady=2)
            save_btn = tk.Button(self.bottom_frame, width=15, text="Uložit",
                                 command=lambda: self.check_before_save(action=action))
            save_btn.pack(side=tk.LEFT, padx=5, pady=5)
            cancel_btn = tk.Button(self.bottom_frame, width=15, text="Zrušit",
                                   command=self.current_view_instance.show_selected_item)
            cancel_btn.pack(side=tk.LEFT, padx=5, pady=5)


    def initialize_title(self, add_name_label=True):
        """
        Vytvoření nadpisu dle typu zobrazovaných dat.
        """
        self.order_of_name = self.curr_table_config["order_of_name"]
        title_label = tk.Label(self.title_frame, bg="yellow", text=self.title, font=self.custom_font)
        title_label.pack(padx=2, pady=2)
        if add_name_label:
            name_text = f"{self.tab2hum[self.col_names[self.order_of_name]]}: \n {str(self.item_values[self.order_of_name])}"
            name_label = tk.Label(self.title_frame, bg="yellow", wraplength=400, font=self.custom_font, text=name_text)
            name_label.pack(padx=2, pady=2)


    def check_before_save(self, action): 
        """
        Metoda pro kontrolu zadání povinných dat a kontrolu správnosti dat před uložením. 

        :Params action: typ prováděné operace.
        """
        for col in self.curr_entry_dict.get("mandatory", []):
            if not self.entries[col].get():
                messagebox.showwarning("Chyba", f"Před uložením nejdříve zadejte položku {self.tab2hum.get(col, col)}")
                self.entries[col].focus()
                return
            
        for col in self.curr_entry_dict.get("not_neg_integer", []):
            entry_val = self.entries[col].get()
            if not entry_val.isdigit() or int(entry_val) < 0:
                messagebox.showwarning("Chyba", f"Položka {self.tab2hum.get(col, col)} musí být celé nezáporné číslo.")
                self.entries[col].focus()
                return
            
        for col in set(self.curr_entry_dict.get("pos_real", [])).union(self.curr_entry_dict.get("not_neg_real", [])):
            entry_val = self.entries[col].get()
            if entry_val:
                try:
                    float_entry_val = float(entry_val)
                    if col in self.curr_entry_dict.get("pos_real", []) and float_entry_val <= 0:
                        messagebox.showwarning("Chyba", f"Položka {self.tab2hum.get(col, col)} musí být kladné reálné číslo s desetinnou tečkou.")
                        return
                    if col in self.curr_entry_dict.get("not_neg_real", []) and float_entry_val < 0:
                        messagebox.showwarning("Chyba", f"Položka {self.tab2hum.get(col, col)} musí být nezáporné reálné číslo s desetinnou tečkou.")
                        return 
                except ValueError:
                    messagebox.showwarning("Chyba", f"Položka {self.tab2hum.get(col, col)} není platné reálné číslo s desetinnou tečkou.")
                    return

        if action=="add":
            if self.current_table=="zarizeni":
                success = self.check_length()
                if not success: return
               
            if self.current_table=='varianty':
                success = self.check_variant_existence()
                if not success: return
            
        self.save_item(action)


    def check_length(self):
        """
        Metoda pro kontrolu délky normalizované zkratky názvu zařízení.
        """
        col = "Zarizeni"
        entry_val = self.entries[col].get()
        normalized = unicodedata.normalize('NFKD', entry_val).encode('ASCII', 'ignore').decode('ASCII')
        final_val = normalized.upper().replace(" ", "_")
        self.entries[col].delete(0, "end")
        self.entries[col].insert(0, final_val)
        if len(final_val) > 8:
            messagebox.showwarning("Varování", f"Zkratka zařízení po normalizaci:\n{final_val}\n je delší než 10 znaků.")
            self.entries[col].focus()
            return False
        self.new_col_name = final_val
        return True


    def check_variant_existence(self):
        """
        Metoda pro kontrolu existence ukládané varianty.
        """
        id_sklad_value = self.entries['id_sklad'].get()
        id_dodavatele_value = self.entries['id_dodavatele'].get()
        exists_variant = self.controller.check_existence_of_variant(id_sklad_value, id_dodavatele_value, self.current_table)
        if exists_variant:
            messagebox.showerror("Chyba", "Tato varianta již existuje.")
            self.entries["Dodavatel"].focus()
            return False
        return True


    def save_item(self, action):
        """
        Metoda na uložení nových / upravených dat v databázi.

        :Params action: typ prováděné operace.
        :Params selected_item_id: v případě akce "edit" je to vybrané ID položky k editaci.
        """
        self.entry_values = {}
        for col, entry in self.entries.items():
            self.entry_values[col] = entry.get()
        
        self.checkbutton_values = {col: (1 if state.get() else 0) for col, state in self.checkbutton_states.items()}
        combined_values = {**self.entry_values, **self.checkbutton_values}
                      
        if action == "add":
            if self.current_table == "varianty":
                col_names_to_save = self.col_names[:-2]
            else: col_names_to_save = self.col_names
            values_to_insert = [combined_values[col] for col in col_names_to_save]
            if self.current_table == 'zarizeni':
                success = self.controller.add_column_and_set_default(self.new_col_name)
                if not success: return
            success = self.controller.insert_new_item(self.current_table, col_names_to_save, values_to_insert)
            if not success: return
            self.id_num = int(self.new_id)
        elif action == "edit" and self.id_num is not None:
            success = self.controller.update_row(self.current_table, self.id_num, self.id_col_name, combined_values)
            if not success: return
        self.controller.show_data(self.current_table, self.id_num)


    def show_for_editing(self):
        """
        Metoda pro zobrazení vybrané položky z Treeview ve frame item_frame pro editaci údajú.
        Název položky je v title_frame, zbylé informace v show_frame
        """        
        self.entries = {}
        self.checkbutton_states = {}
                  
        for index, col in enumerate(self.col_names):
            if col in self.check_columns:
                frame = tk.Frame(self.right_frame)
                if self.item_values:
                    self.checkbutton_states[col] = tk.BooleanVar(value=self.item_values[index] == 1)
                else:
                    self.checkbutton_states[col] = tk.BooleanVar(value=True) if col == 'Ucetnictvi' else tk.BooleanVar(value=False)
                if col in self.special_columns:
                    frame = tk.Frame(self.right_top_frame)
                    checkbutton = tk.Checkbutton(frame, text=self.tab2hum.get(col, col), borderwidth=3,
                                                 relief="groove", variable=self.checkbutton_states[col])
                else:
                    frame = tk.Frame(self.right_frame)
                    checkbutton = tk.Checkbutton(frame, text=self.tab2hum.get(col, col),
                                                 variable=self.checkbutton_states[col])
                checkbutton.pack(side=tk.LEFT, padx=5)
            else:
                frame = tk.Frame(self.left_frame)
                label = tk.Label(frame, text=self.tab2hum.get(col, col), width=12)
                label.pack(side=tk.LEFT)
                start_value = self.item_values[index] if self.item_values else ""
                match col:                          
                    case 'Min_Mnozstvi_ks' | 'Min_obj_mnozstvi':
                        entry = tk.Spinbox(frame, from_=0, to='infinity')
                        if self.item_values:
                            entry.delete(0, "end")
                            entry.insert(0, self.item_values[index])
                    case 'Jednotky':
                        entry = ttk.Combobox(frame, values=self.unit_tuple)
                        entry.set(start_value)                         
                    case 'Dodavatel' if self.current_table in ['sklad', 'varianty']:
                        entry = ttk.Combobox(frame, values=self.suppliers)
                        entry.set(start_value)
                        if self.current_table=='varianty':
                            entry.bind("<<ComboboxSelected>>", lambda event, entry=entry: self.supplier_number(entry))
                    case _:
                        entry = tk.Entry(frame)
                        if self.item_values:
                            entry.insert(0, self.item_values[index])                                              
                entry.pack(fill=tk.X, padx=2, pady=3)
                entry.bind('<Return>', lambda event: self.check_before_save(action=self.action))
                entry.bind('<Escape>', lambda event: self.current_view_instance.show_selected_item())
                self.entries[col] = entry
                if col in self.curr_entry_dict.get("mandatory", []): entry.config(background='yellow') 
                if col in self.curr_entry_dict.get("insert", []): entry.insert(0, self.curr_entry_dict["insert"][col])
                if col in self.curr_entry_dict.get("read_only", []): entry.config(state='readonly')
                if col in self.curr_entry_dict.get("pack_forget", []):
                    label.pack_forget()
                    entry.pack_forget()
            frame.pack(fill=tk.X)
        self.entries[self.curr_table_config["focus"]].focus()


    def supplier_number(self, entry=None):
        """
        Metoda na vložení čísla dodavatele do entry pro id_dodavatele dle vybraného dodavatele v comboboxu.
        """
        supplier_id = self.suppliers_dict[entry.get()]
        idd = "id_dodavatele"
        self.entries[idd].config(state='normal')
        self.entries[idd].delete(0, 'end')
        self.entries[idd].insert(0, supplier_id)
        self.entries[idd].config(state='readonly')


class ItemFrameShow(ItemFrameBase):
    """
    Třída ItemFrameShow se stará o zobrazení vybraných položek.
    """
    def __init__(self, master, controller, col_names, tab2hum, current_table, check_columns):
        """
        Inicializace prvků v item_frame.
        
        :param: Inicializovány v rodičovské třídě.
        """
        super().__init__(master, controller, col_names, tab2hum, current_table, check_columns)


    def clear_item_frame(self):
        """
        Odstranění všech widgetů v title_frame a show_frame
        """
        for widget in self.title_frame.winfo_children():
            widget.destroy()
        for widget in self.show_frame.winfo_children():
            widget.destroy()  


    def init_curr_dict(self):
        """
        Metoda pro přidání slovníku hodnotami přiřazenými dle aktuální tabulky.
        """        
        self.entry_dict = {}
        self.curr_entry_dict = self.entry_dict.get(self.current_table, {})
        self.title = "ZOBRAZENÍ " + str(self.curr_table_config["name"])
                           

    def show_selected_item_details(self, item_values):
        """
        Metoda pro zobrazení vybrané položky z Treeview ve frame item_frame
        Název položky je v title_frame, zbylé informace v show_frame.

        :param item_values: n-tice řetězců obsahující hodnoty sloupců označené položky.
        """
        self.item_values = item_values
        self.clear_item_frame()
        self.init_curr_dict()
        self.initialize_title()
        self.update_frames(action=None)
        self.checkbutton_states = {}
 
        for index, col in enumerate(self.col_names):
            if index == self.order_of_name: continue   # Vynechá název
            item_value = self.item_values[index]
            item_text = self.tab2hum.get(col, col)
            if col in self.check_columns:
                item_state = int(item_value) == 1
                self.checkbutton_states[col] = tk.BooleanVar(value=item_state)
                if col in self.special_columns:
                    frame = tk.Frame(self.right_top_frame)
                    checkbutton = tk.Checkbutton(frame, text=item_text, borderwidth=3, relief="groove",
                                                 variable=self.checkbutton_states[col])
                else:
                    frame = tk.Frame(self.right_frame)
                    checkbutton = tk.Checkbutton(frame, text=item_text, variable=self.checkbutton_states[col])
                checkbutton.pack(side=tk.LEFT, padx=5)
                checkbutton.bind("<Enter>", lambda event, cb=checkbutton: cb.config(state="disabled"))
                checkbutton.bind("<Leave>", lambda event, cb=checkbutton: cb.config(state="normal"))
            else:
                frame = tk.Frame(self.left_frame)
                label_text = f"{item_text}:\n{item_value}"
                label = tk.Label(frame, text=label_text, borderwidth=2, relief="ridge", wraplength=250)
                label.pack(fill=tk.X)
            frame.pack(fill=tk.X)              

       
class ItemFrameEdit(ItemFrameBase):
    """
    Třída ItemFrameEdit se stará o úpravu vybraných položek.
    """
    def __init__(self, master, controller, col_names, tab2hum, current_table, check_columns, current_view_instance):
        """
        Inicializace prvků v item_frame.
        
        :param: Inicializovány v rodičovské třídě.
        """
        super().__init__(master, controller, col_names, tab2hum, current_table, check_columns)
        self.current_view_instance = current_view_instance
        self.action = 'edit'
        self.update_frames(action=self.action)
        
       
    def init_curr_dict(self):
        """
        Metoda pro přidání slovníku hodnotami přiřazenými dle aktuální tabulky.
        """
        self.entry_dict = {"sklad": {"read_only": ('Evidencni_cislo', 'Mnozstvi_ks_m_l', 'Jednotky', 'Dodavatel',
                                                   'Datum_nakupu', 'Jednotkova_cena_EUR', 'Celkova_cena_EUR'),
                                     "mandatory": ('Min_Mnozstvi_ks', 'Nazev_dilu',),
                                     "not_neg_integer": ('Interne_cislo', 'Min_Mnozstvi_ks',),
                                     },
                           "dodavatele": {"read_only": ('id', 'Dodavatel'),
                                          },
                           "zarizeni": {"read_only": ('id', 'Zarizeni'),
                                        "mandatory": ('Zarizeni', 'Nazev_zarizeni', 'Umisteni', 'Typ_zarizeni',),
                                        },                           
                           "varianty": {"read_only": ('id', 'id_sklad', 'id_dodavatele',),
                                        "mandatory": ('Nazev_varianty', 'Cislo_varianty',),
                                        "not_neg_real":('Jednotkova_cena_EUR',),
                                        "not_neg_integer": ('Dodaci_lhuta', 'Min_obj_mnozstvi'),
                                        }
                           }
        self.curr_entry_dict = self.entry_dict.get(self.current_table, {})
        self.title = "ÚPRAVA " + str(self.curr_table_config["name"])        


    def open_edit_window(self, item_values):
        """
        Metoda pro úpravu vybrané položky z Treeview.

        :params item_values: Aktuální hodnoty z databázové tabulky dle id vybrané položky z Treeview.
        """
        self.item_values = item_values
        self.init_curr_dict()        
        self.initialize_title()       
        self.id_num = self.item_values[0]
        self.id_col_name = self.curr_table_config.get("id_col_name", "id")
        self.show_for_editing()


class ItemFrameAdd(ItemFrameBase):
    """
    Třída ItemFrameAdd se stará o tvorbu nových položek.
    """
    def __init__(self, master, controller, col_names, tab2hum, current_table, check_columns, current_view_instance):
        """
        Inicializace prvků v item_frame.
        
        :param: Inicializovány v rodičovské třídě.
        """
        super().__init__(master, controller, col_names, tab2hum, current_table, check_columns)
        self.current_view_instance = current_view_instance
        self.action = 'add'
        self.update_frames(action=self.action)        


    def init_curr_dict(self):
        """
        Metoda pro přidání slovníku hodnotami přiřazenými dle aktuální tabulky.
        """
        self.actual_date = datetime.now().strftime("%Y-%m-%d")
        self.entry_dict = {"sklad": {"read_only": ('Evidencni_cislo', 'Interne_cislo', 'Mnozstvi_ks_m_l', 'Jednotkova_cena_EUR',
                                                   'Celkova_cena_EUR', 'Objednano', 'Cislo_objednavky', 'Jednotky', 'Dodavatel',),
                                     "pack_forget": ('Objednano', 'Mnozstvi_ks_m_l', 'Datum_nakupu', 'Cislo_objednavky',
                                                     'Jednotkova_cena_EUR', 'Celkova_cena_EUR',),
                                     "insert": {'Evidencni_cislo': self.new_id, 'Interne_cislo': self.new_interne_cislo, 'Mnozstvi_ks_m_l': '0',
                                                'Jednotkova_cena_EUR': '0.0', 'Celkova_cena_EUR': '0.0',},
                                     "mandatory": ('Min_Mnozstvi_ks', 'Nazev_dilu', 'Jednotky',),
                                     "not_neg_integer":('Min_Mnozstvi_ks',),
                                     },                                 
                           "dodavatele": {"read_only": ('id',),
                                          "insert": {'id': self.new_id},
                                          "mandatory": ('Dodavatel',),
                                          },
                           "zarizeni": {"read_only": ('id',),
                                        "insert": {'id': self.new_id},
                                        "mandatory": ('Zarizeni', 'Nazev_zarizeni', 'Umisteni', 'Typ_zarizeni',),
                                        },                            
                           "varianty": {"read_only": ('id','Nazev_dilu', 'id_sklad', 'Dodavatel', 'id_dodavatele',),
                                        "mandatory": ('Nazev_varianty', 'Cislo_varianty', 'Dodavatel', 'Jednotkova_cena_EUR',),
                                        "insert": {'Dodaci_lhuta': 0, 'Min_obj_mnozstvi':0,},
                                        "not_neg_real":('Jednotkova_cena_EUR',),
                                        "not_neg_integer": ('Dodaci_lhuta', 'Min_obj_mnozstvi'),
                                        "calculate": 'id_dodavatele',
                                        },
                           }
        self.curr_entry_dict = self.entry_dict.get(self.current_table, {})
        self.title = "VYTVOŘENÍ " + str(self.curr_table_config["name"])        


    def add_item(self, new_id, new_interne_cislo):
        """
        Metoda pro přidání nové položky do aktuální tabulky.
        """
        self.item_values = None
        self.new_id = new_id
        self.new_interne_cislo = new_interne_cislo
        self.init_curr_dict()
        self.initialize_title(add_name_label=False)
        self.show_for_editing()


    def add_variant(self, item_values):
        """
        Metoda pro vytvoření nové varianty podle vybrané položky z Treeview.
        Název položky je v title_frame, zbylé informace v show_frame

        :params item_values: Aktuální hodnoty z databázové tabulky dle id vybrané položky z Treeview.        
        """        
        self.entries = {}
        self.new_id = None
        self.new_interne_cislo = None
        self.item_values = item_values
        dodavatel_value = self.item_values[-1]
        if dodavatel_value:
            id_dodavatele_value = self.suppliers_dict[dodavatel_value]
            self.item_values[2] = id_dodavatele_value
        self.init_curr_dict()        
        self.initialize_title(add_name_label=False)       
        self.show_for_editing()
                

class ItemFrameMovements(ItemFrameBase):
    """
    Třída ItemFrameMovements se stará o příjem a výdej ve skladě.
    """
    def __init__(self, master, controller, col_names, tab2hum, current_table, check_columns, current_view_instance):
        """
        Inicializace prvků v item_frame.
        
        :param: Inicializovány v rodičovské třídě.
        """
        super().__init__(master, controller, col_names, tab2hum, current_table, check_columns)
        self.current_view_instance = current_view_instance
        
       
    def init_curr_dict(self):
        """
        Metoda pro přidání slovníku hodnotami přiřazenými dle aktuální tabulky.
        """
        self.actual_date = datetime.now().strftime("%Y-%m-%d")
        self.action_dict = {
            "sklad": {"prijem": {"grid_forget": ('Nazev_dilu', 'Celkova_cena_EUR', 'Pouzite_zarizeni',
                                                 'Datum_vydeje', 'Cas_operace', 'id'),
                                 "mandatory": ('Zmena_mnozstvi', 'Umisteni', 'Dodavatel', 'Cislo_objednavky'),
                                 "date":('Datum_nakupu',),
                                 "pos_real": ('Jednotkova_cena_EUR',),
                                 "pos_integer":('Zmena_mnozstvi',),
                                 "actual_value": {'Typ_operace': "PŘÍJEM", 'Operaci_provedl': self.name_of_user,
                                                  'Datum_nakupu': self.actual_date, 'Datum_vydeje': "",},
                                 "tuple_values_to_save": ('Objednano', 'Mnozstvi_ks_m_l', 'Umisteni', 'Dodavatel', 'Datum_nakupu',
                                                          'Cislo_objednavky', 'Jednotkova_cena_EUR', 'Celkova_cena_EUR', 'Poznamka'),
                                 },
                      "vydej": {"grid_forget": ('Nazev_dilu', 'Celkova_cena_EUR', 'Objednano', 'Dodavatel', 'Cas_operace',
                                                'Cislo_objednavky', 'Jednotkova_cena_EUR', 'Datum_nakupu', 'id'),
                                "mandatory": ('Zmena_mnozstvi', 'Pouzite_zarizeni', 'Umisteni'),
                                "date":('Datum_vydeje',),
                                "pos_integer":('Zmena_mnozstvi',),
                                "actual_value": {'Typ_operace': "VÝDEJ", 'Operaci_provedl': self.name_of_user,
                                                  'Datum_nakupu': "", 'Datum_vydeje': self.actual_date,},
                                "tuple_values_to_save": ('Mnozstvi_ks_m_l', 'Umisteni', 'Poznamka', 'Celkova_cena_EUR'),
                                },
                      },
            }              
        self.title = self.action_dict[self.current_table][self.action]["actual_value"]['Typ_operace']
        self.entry_dict = {"sklad": {"read_only": ('Ucetnictvi', 'Evidencni_cislo', 'Interne_cislo', 'Jednotky',
                                                   'Mnozstvi_ks_m_l', 'Typ_operace', 'Operaci_provedl', 'Pouzite_zarizeni',
                                                   'Dodavatel'),
                                     "insert_item_value": ('Ucetnictvi', 'Evidencni_cislo', 'Interne_cislo', 'Jednotky',
                                                           'Mnozstvi_ks_m_l', 'Umisteni', 'Jednotkova_cena_EUR', 'Objednano',
                                                           'Poznamka', 'Nazev_dilu'),
                                     },
                           }
        self.title = f"{self.title} ZBOŽÍ"       
        self.curr_entry_dict = self.entry_dict[self.current_table] | self.action_dict[self.current_table][self.action]
        self.devices = tuple(self.controller.fetch_dict("zarizeni").keys())


    def init_item_movements(self, action, item_values, audit_log_col_names):
        """
        Metoda pro inicializace proměnných pro příjem a výdej skladových položek.

        :params action: Parametr s názvem akce příjem nebo výdej zboží - "prijem", "vydej".
                item_values: Aktuální hodnoty z databázové tabulky dle id vybrané položky z Treeview.
                audit_log_col_names: N-tice názvů sloupců tabulky audit_log.      
        """
        self.action = action
        self.item_values = item_values
        self.audit_log_col_names = audit_log_col_names
        self.init_curr_dict()
        self.initialize_title()
        self.update_frames(action=self.action)         
        self.id_num = self.item_values[0]
        self.id_col_name = self.curr_table_config.get("id_col_name", "id")
        self.entries_al = {}
        self.actual_quantity = int(self.item_values[self.curr_table_config["quantity_col"]])
        self.actual_unit_price = float(self.item_values[self.curr_table_config["unit_price_col"]])


    def enter_item_movements(self, action, item_values, audit_log_col_names):
        """
        Metoda pro příjem a výdej skladových položek.

        :params action: Parametr s názvem akce příjem nebo výdej zboží - "prijem", "vydej".
                item_values: Aktuální hodnoty z databázové tabulky dle id vybrané položky z Treeview.
                audit_log_col_names: N-tice názvů sloupců tabulky audit_log.    
        """
        self.init_item_movements(action, item_values, audit_log_col_names)
        
        if self.action=='vydej' and self.actual_quantity==0:
            self.current_view_instance.show_selected_item()
            messagebox.showwarning("Chyba", f"Položka aktuálně není na skladě, nelze provést výdej!")
            return
        
        for idx, col in enumerate(self.audit_log_col_names):
            if col in self.col_names:
                index = self.col_names.index(col)
            self.left_frame.columnconfigure(1, weight=1)
            label = tk.Label(self.left_frame, text=self.tab2hum.get(col, col))
            label.grid(row=idx, column=0, sticky="ew", padx=5, pady=2)
            if col == 'Pouzite_zarizeni':
                entry_al = ttk.Combobox(self.left_frame,values=self.devices+("Neuvedeno",))             
                entry_al.set("")
            elif col == 'Dodavatel':
                entry_al = ttk.Combobox(self.left_frame, values=self.suppliers)
                entry_al.set(self.item_values[index])
            else:
                entry_al = tk.Entry(self.left_frame)                        
            entry_al.grid(row=idx, column=1, sticky="ew", padx=5, pady=2)
            entry_al.bind('<Return>', lambda event: self.check_before_save(action=self.action))
            entry_al.bind('<Escape>', lambda event: self.current_view_instance.show_selected_item())
            
            if col in self.curr_entry_dict.get("mandatory",[]): entry_al.config(background='yellow')
            if col in self.curr_entry_dict.get("insert_item_value",[]): entry_al.insert(0, self.item_values[index])        
            if col in self.curr_entry_dict.get("actual_value",[]): entry_al.insert(0, self.curr_entry_dict["actual_value"][col])
            if col in self.curr_entry_dict.get("read_only",[]): entry_al.config(state='readonly')                
            if col in self.curr_entry_dict.get("grid_forget",[]):
                label.grid_forget()
                entry_al.grid_forget()
            self.entries_al[col] = entry_al
            
        self.entries_al['Zmena_mnozstvi'].focus()


    def show_warning(self, col, warning):
        """
        Metoda pro vypsání varování a zaměření pozornosti na vstupní pole s chybným zadáním.

        :parames col: název nesprávně zadané položky.
        :parames warning: text vypsaného varování.
        """
        messagebox.showwarning("Chyba", warning)
        self.entries_al[col].focus()


    def check_before_save(self, action): 
        """
        Metoda pro kontrolu zadání povinných dat a kontrolu správnosti dat před uložením. 

        :Params action: typ prováděné operace.
        """
        self.action = action
        
        for col in self.curr_entry_dict.get("mandatory", []):
            if not self.entries_al[col].get():
                self.show_warning(col, f"Před uložením nejdříve zadejte položku {self.tab2hum.get(col, col)}")
                return
            
        for col in self.curr_entry_dict.get("pos_integer", []):
            entry_val = self.entries_al[col].get()
            if not entry_val.isdigit() or int(entry_val) <= 0:
                self.show_warning(col, f"Položka {self.tab2hum.get(col, col)} musí být kladné celé číslo.")
                return

        self.quantity_change = int(self.entries_al['Zmena_mnozstvi'].get())
        self.quantity = int(self.entries_al['Mnozstvi_ks_m_l'].get())

        if self.action=='vydej' and self.quantity_change > self.quantity:
                self.show_warning('Zmena_mnozstvi', "Vydávané množství je větší než množství na skladě.")
                return

        for col in self.curr_entry_dict.get("pos_real", []):
            entry_val = self.entries_al[col].get()
            try:
                float_entry_val = float(entry_val)
                if float_entry_val <= 0:
                    self.show_warning(col, f"Položka {self.tab2hum.get(col, col)} musí být kladné reálné číslo s desetinnou tečkou.")
                    return
            except ValueError:
                self.show_warning(col, f"Položka {self.tab2hum.get(col, col)} není platné kladné reálné číslo s desetinnou tečkou.")
                return

        for col in self.curr_entry_dict.get("date", []):
            date_str = self.entries_al[col].get()
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                self.show_warning(col, "Datum nákupu musí být ve formátu RRRR-MM-DD.")
                return
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                self.show_warning(col, f"Neplatné datum: {date_str}. Zadejte prosím platné datum.")
                return

        self.calculate_and_save(action)


    def calculate_and_save(self, action): 
        """
        Metoda uložení dat výpočet hodnot před uložením do skladu a audit_logu a pro uložení
        změn do tabulky sklad a nového zápisu do tabulky audit_log. Pokud je při příjmu zjištěno,
        že ještě neexistuje varianta skladové položky se zadaným dodavatelem, tak připraví okno na
        vytvoření nové varianty.
        
        :Params action: typ prováděné operace.
        """           
        self.calculate_before_save_to_audit_log() 
        self.calculate_before_save_to_sklad()
        
        success = self.controller.update_row("sklad", self.id_num, self.id_col_name, self.values_to_sklad)
        if not success:
            return
        success = self.controller.insert_new_item("audit_log", self.audit_log_col_names[1:], self.values_to_audit_log[1:])
        if not success:
            return
        messagebox.showinfo("Informace", f"Úspěšně proběhl {self.title.lower()} a zápis do audit logu!")

        if self.action == "prijem":
            id_sklad_value = self.id_num
            dodavatel_value = self.values_to_sklad["Dodavatel"]
            id_dodavatele_value = self.suppliers_dict[dodavatel_value]
            exists_variant = self.controller.check_existence_of_variant(id_sklad_value, id_dodavatele_value, "varianty")
            if not exists_variant:
                messagebox.showinfo("Informace", "Varianta s tímto dodavatelem ještě neexistuje, prosím, vytvořte ji.")
                self.current_view_instance.add_variant(curr_unit_price=self.new_unit_price)
                return
            else:
                pass # uložit aktuální jednotkovou cenu do varianty

        self.controller.show_data(self.current_table, self.id_num)
        

    def calculate_before_save_to_audit_log(self):
        """
        Vypočítá hodnoty před uložením do audit logu.
        
        Tato metoda upraví hodnoty pro změnu množství, jednotkovou cenu a celkovou cenu operace,
        a také aktualizuje nové množství na skladě. Výsledné hodnoty jsou připraveny k uložení do audit logu.
        """
        self.new_unit_price = float(self.entries_al['Jednotkova_cena_EUR'].get())
        
        if self.action == 'vydej': 
            self.quantity_change = -self.quantity_change
        self.total_price = self.new_unit_price * self.quantity_change
        self.new_quantity = self.quantity + self.quantity_change

        self.values = {col: entry_al.get() for col, entry_al in self.entries_al.items()}
        self.values['Cas_operace'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")    
        self.values['Zmena_mnozstvi'] = self.quantity_change
        self.values['Celkova_cena_EUR'] = self.total_price
        self.values['Mnozstvi_ks_m_l'] = self.new_quantity
        
        self.values_to_audit_log = [self.values[col] for col in self.audit_log_col_names]
        

    def calculate_before_save_to_sklad(self):
        """
        Upravuje a připravuje hodnoty pro uložení do tabulky sklad v závislosti na provedené akci (příjem/výdej).

        Výpočet nové celkové ceny a průměrné jednotkové ceny pro příjem a aktualizace celkové ceny pro výdej.
        Změny jsou reflektovány ve slovníku `self.values`, který je poté použit pro aktualizaci záznamu v databázi.
        """
        if self.action == 'prijem':
            if self.actual_quantity > 0:
                new_total_price = round(self.actual_quantity*self.actual_unit_price+self.quantity_change*self.new_unit_price, 1)
                average_unit_price = round(new_total_price / (self.actual_quantity + self.quantity_change), 2)
                self.values['Celkova_cena_EUR'] = new_total_price
                self.values['Jednotkova_cena_EUR'] = average_unit_price
        elif self.action == 'vydej': 
            self.values['Celkova_cena_EUR'] = round(self.new_quantity * self.actual_unit_price, 1)

        self.values_to_sklad = {col: self.values[col] for col in self.curr_entry_dict["tuple_values_to_save"] if col in self.values}



class Controller:
    """
    Třída Controller koordinuje Model a View.
    """
    def __init__(self, root, db_path):
        """
        Inicializace controlleru s připojením k databázi a inicializací GUI.
        
        :param root: Hlavní okno aplikace.
        :param db_path: Cesta k databázovému souboru.
        """
        self.root = root
        self.db_path = db_path
        self.model = Model(db_path)
        self.current_view_instance = None
        self.varianty_view_instance = None
        self.current_user = None
        self.current_role = None


    def fetch_dict(self, table):
        """
        Získání seznamu dodavatelů nebo zařízení'.

        :param table: pro výběr tabulky, ze které se získávají data.
        :return slovník dodavatelů nebo zařízení s jejich id jako hodnotou.
        """
        data = self.model.fetch_data(table)
        if table == "sklad":
            name=6
        else: name=1
        return {row[name]: row[0] for row in data}


    def get_max_id(self, curr_table, id_col_name):
        """
        Získání nejvyššího evidenčního čísla z tabulky 'sklad'.

        :param id_col: Číslo sloupce, ve kterém jsou id čísla pro danou tabulku.
        :return Nejvyšší hodnotu ve sloupci 'Evidencni_cislo' v tabulce sklad.
        """
        return self.model.get_max_id(curr_table, id_col_name)
    

    def show_data(self, table, current_id_num=None):
        """
        Získání a zobrazení dat z vybrané tabulky v GUI. Pokud se mění tabulka k zobrazení,
        vytvoří se nová instance podtřídy View, pokud zůstává tabulka
        stejná, pouze se aktulizují zobrazená data.
        
        :param table: Název tabulky pro zobrazení.
        """     
        if table == 'varianty':
            data = self.model.fetch_varianty_data()
            col_names = list(self.model.fetch_col_names(table)) + ["Nazev_dilu", "Dodavatel", "Pod_minimem"]
        elif table == 'sklad':
            data = self.model.fetch_sklad_data()
            col_names = list(self.model.fetch_col_names(table)) + ["Pod_minimem"]
        else:
            data = self.model.fetch_data(table)
            col_names = self.model.fetch_col_names(table)

        if self.current_table != table:
            self.current_table = table
            self.current_view_instance.frame.destroy()
            if table == "sklad":
                self.current_view_instance = SkladView(self.root, self, col_names)
            elif table == "audit_log":
                self.current_view_instance = AuditLogView(self.root, self, col_names)
            elif table == "dodavatele":
                self.current_view_instance = DodavateleView(self.root, self, col_names)
            elif table == "varianty":
                self.current_view_instance = VariantyView(self.root, self, col_names)
            elif table == "zarizeni":
                self.current_view_instance = ZarizeniView(self.root, self, col_names)
            elif table == "uzivatele":
                self.current_view_instance = UzivateleView(self.root, self, col_names)                
            else:
                messagebox.showwarning("Varování", "Nebyla vytvořena nová instance třídy View.")
                return
        
        if current_id_num:
            self.current_view_instance.add_data(data, current_id_num=current_id_num)
        else:
            self.current_view_instance.add_data(data)


    def show_data_for_editing(self, table, id_num, id_col_name, master, tab2hum, check_columns):
        """
        Získání dat a zobrazení vybrané položky pro úpravu. Vytvoří se nová instance ItemFrameEdit.
        
        :param table: Název tabulky pro zobrazení.
        :param id_num: Identifikační číslo položky pro zobrazení.
        """
        item_values = self.model.fetch_item_for_editing(table, id_num, id_col_name)
        col_names = self.model.fetch_col_names(table)
        
        self.current_item_instance = ItemFrameEdit(master, self, col_names, tab2hum, table,
                                                       check_columns, self.current_view_instance)
        self.current_item_instance.open_edit_window(item_values)


    def start_login(self):
        """
        Metoda pro spuštění přihlašování uživatele. Vytvoří se nová instance LoginView.
        """
        # při programování pro přeskočení přihlašování, potom vyměnit za okomentovaný kód
        self.current_table = "sklad"
        data = self.model.fetch_sklad_data()
        col_names = list(self.model.fetch_col_names(self.current_table)) + ["Pod_minimem"]
        self.current_view_instance = SkladView(self.root, self, col_names)
        self.current_view_instance.add_data(data)
        self.current_user = "pilat"
        self.name_of_user = "Zdeněk Pilát"
        if sys.platform.startswith('win'):
            self.root.state('zoomed')
        else:
            window_width=1920
            window_height=1080
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            center_x = int((screen_width/2) - (window_width/2))
            center_y = int((screen_height/2) - (window_height/2))
            self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

        
##        self.current_table = "login"
##        self.current_view_instance = LoginView(self.root, self, [])


    def attempt_login(self, username, password_hash):
        """
        Zkusí přihlásit uživatele se zadanými přihlašovacími údaji.
        
        :param username: Uživatelské jméno.
        :param password_hash: Zahashované heslo.
        """        
        if self.model.verify_user_credentials(username, password_hash):
            self.current_user = username
            self.name_of_user, self.current_role = self.model.get_user_info(self.current_user)
            self.current_view_instance.start_main_window()
        else:
            self.current_view_instance.handle_failed_login()


    def show_data_for_movements(self, table, id_num, id_col_name, master, tab2hum, check_columns, action):
        """
        Získání dat a zobrazení vybrané položky pro skladový pohyb. Vytvoří se nová instance ItemFrameMovements.
        
        :param table: Název tabulky pro zobrazení.
        :param id_num: Identifikační číslo položky pro zobrazení.
        """
        item_values = self.model.fetch_item_for_editing(table, id_num, id_col_name)
        col_names = self.model.fetch_col_names(table)
        audit_log_col_names = self.model.fetch_col_names("audit_log")

        self.current_item_instance = ItemFrameMovements(master, self, col_names, tab2hum, table,
                                                        check_columns, self.current_view_instance)
        self.current_item_instance.enter_item_movements(action, item_values, audit_log_col_names)


    def add_item(self, table, id_num, id_col_name, master, tab2hum, check_columns):
        """
        Získání dat a zobrazení vybrané položky pro úpravu. Pokud se mění tabulka k zobrazení,
        vytvoří se nová instance podtřídy ItemFrameBase, pokud zůstává tabulka stejná,
        pouze se aktulizují zobrazená data.
        
        :param table: Název tabulky pro zobrazení.
        :param id_num: Identifikační číslo položky pro zobrazení.
        """
        new_interne_cislo = str(self.model.get_max_interne_cislo() + 1) if table=="sklad" else None
        new_id = str(self.model.get_max_id(table, id_col_name) + 1)
        col_names = self.model.fetch_col_names(table)
        
        self.current_item_instance = ItemFrameAdd(master, self, col_names, tab2hum, table,
                                                  check_columns, self.current_view_instance)
        self.current_item_instance.add_item(new_id, new_interne_cislo)


    def add_variant(self, table, id_num, id_col_name, master, tab2hum, varianty_check_columns,
                    varianty_table, varianty_id_col_name, curr_unit_price):
        """
        Získání dat a zobrazení vybrané položky pro vytvoření nové varianty.
        
        :param table: Název tabulky pro zobrazení.
        :param id_num: Identifikační číslo položky pro zobrazení.
        """
        sklad_item_values = self.model.fetch_item_for_editing(table, id_num, id_col_name)
        sklad_col_names = self.model.fetch_col_names(table)
        sklad_values_dict = {keys: values for keys, values in zip(sklad_col_names, sklad_item_values)}
        varianty_col_names = list(self.model.fetch_col_names(varianty_table)) + ["Nazev_dilu", "Dodavatel"]
        new_id = str(self.model.get_max_id(varianty_table, varianty_id_col_name) + 1)
        varianty_item_values = [sklad_values_dict.get(col, "") for col in varianty_col_names]
        varianty_item_values[0] = new_id
        varianty_item_values[1] = sklad_values_dict['Evidencni_cislo']
        varianty_item_values[5] = curr_unit_price if curr_unit_price else ""
                                         
        self.current_item_instance = ItemFrameAdd(master, self, varianty_col_names, tab2hum, varianty_table,
                                                   varianty_check_columns, self.current_view_instance)
        self.current_item_instance.add_variant(varianty_item_values)


    def show_item_variants(self, id_num, frame):
        """
        Metoda, která získá data variant dvojklikem vybrané skladové položky a
        pošle je k zobrazení do item_frame.

        :param id_num: evideční číslo dvojklikem vybrané skladové položky.
        :return 
        """
        table = "varianty"
        id_col_name = "id_sklad"
        if self.varianty_view_instance:
            self.varianty_view_instance.frame.destroy()
        try:
            variants_data = self.model.fetch_item_variants(table, id_num, id_col_name)
            col_names = list(self.model.fetch_col_names(table)) + ["Dodavatel"]
        except Exception as e:
            messagebox.showwarning("Varování", f"Nebyla získána data variant z důvodu chyby:\n {e}")
            return
        if not variants_data:
            return
        self.varianty_view_instance = ItemVariantsView(frame, self, col_names)
        self.varianty_view_instance.add_data(variants_data)  


    def check_existence_of_variant(self, id_sklad_value, id_dodavatele_value, current_table):
        """
        Metoda, která ověří, zda varianta už neexistuje před uložením nové.

        :return True, když varianta už v tabulce "varianty" existuje, jinak False.
        """
        try:
            exists_variant = self.model.check_existence(id_sklad_value, id_dodavatele_value, current_table)
        except Exception as e:
            messagebox.showwarning("Varování", f"Nebyla získána data variant z důvodu chyby:\n {e}")
            return False           
        return exists_variant


    def insert_new_item(self, table, columns, values_to_insert):
        """
        Pokusí se vložit novou položku do zadané tabulky databáze. Pokud operace selže kvůli
        porušení omezení integrity (např. pokusu o vložení položky s již existujícím
        unikátním identifikátorem), zobrazí se uživatelské varování.

        :param table: Název tabulky v databázi, do které se má vložit nová položka.
        :param columns: Seznam názvů sloupců, do kterých se mají vložit hodnoty.
        :param values_to_insert: Seznam hodnot odpovídajících názvům sloupců v `columns`, které se mají vložit.
        :return: Vrátí True, pokud byla položka úspěšně vložena. V případě, že operace selže kvůli
                 porušení omezení integrity, zobrazí varování a vrátí False.
        """
        try:
            self.model.insert_item(table, columns, values_to_insert)
        except sqlite3.IntegrityError:
            messagebox.showwarning("Varování", "Položka se zadaným ID číslem už v databázi existuje.")
            return False
        return True     


    def update_row(self, table, selected_item_id, id_col_name, combined_values):
        """
        Aktualizuje položku v zadané tabulce databáze na základě jejího identifikátoru.

        :param table: Název tabulky, ve které se má aktualizovat položka.
        :param selected_item_id: Hodnota identifikátoru (ID) položky, která se má aktualizovat.
        :param id_col_name: Název sloupce, který obsahuje ID položky.
        :param combined_values: Slovník obsahující aktualizované hodnoty položky, kde klíče jsou názvy sloupců a hodnoty jsou nové hodnoty pro tyto sloupce.
        :return: Vrací True, pokud aktualizace proběhla úspěšně, jinak False.
        """
        try:
            self.model.update_row(table, selected_item_id, id_col_name, combined_values)
        except Exception as e:
            messagebox.showwarning("Varování", f"Chyba při ukládání dat do databáze: {e}!")
            return False
        return True


    def delete_row(self, evidencni_cislo):
        """
        Vymazání položky vybrané v treeview - pouze nulová poslední zadaná položka.
        """
        try:
            self.model.delete_row(evidencni_cislo)
        except Exception as e:
            messagebox.showwarning("Varování", f"Chyba při ukládání dat do databáze: {e}!")
            return False
        return True


    def add_column_and_set_default(self, new_col_name):
        """
        Řídí proces přidání nového sloupce do tabulky 'sklad' a nastavení jeho výchozích hodnot.

        :param new_col_name: Název nového sloupce, který má být přidán.
        """
        try:
            self.model.add_integer_column_with_default(new_col_name)
            messagebox.showinfo("Informace",
                                f"Sloupec {new_col_name} byl úspěšně přidán do tabulky sklad s výchozími hodnotami 0.")
        except Exception as e:
            messagebox.showerror("Chyba", f"Nastala chyba při přidávání sloupce {new_col_name}: {e}")
            return False
        return True            
    

    def export_csv(self, table=None, tree=None):
        """
        Export dat z vybrané tabulky v GUI.
        
        :param table: Název tabulky pro zobrazení.
        """
        csv_file_name = filedialog.asksaveasfilename(defaultextension=".csv",
                                                     filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],)
        if not csv_file_name:
            return

        if tree:
            col_ids = tree["columns"]
            col_names = [tree.heading(col)["text"] for col in col_ids]
            data = [tree.item(item)["values"] for item in tree.get_children()]
        else:    
            col_names = self.model.fetch_col_names(table)
            data = self.model.fetch_data(table)

        try:
            with open(csv_file_name, mode='w', newline='', encoding='utf-8') as csv_file:
                csv_writer = csv.writer(csv_file)    
                csv_writer.writerow(col_names)
                for row in data:
                    csv_writer.writerow(row)
            messagebox.showinf("Export dokončen", f"Data byla úspěšně exportována do souboru '{csv_file_name}'.")
        except Exception as e:
            messagebox.showerror("Chyba při exportu", f"Nastala chyba při exportu dat: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    root.title('Přihlášení - Skladová databáze HPM HEAT SK')
    db_path = 'skladova_databaze_EC0.db' 
    controller = Controller(root, db_path)
    controller.start_login()
    root.mainloop()
