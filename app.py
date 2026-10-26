import os, json, hashlib, secrets, hmac
from datetime import date, datetime
from pathlib import Path
from io import BytesIO
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

BASE = Path(__file__).parent
st.set_page_config(page_title='Vidu Saviya | CSR Management', page_icon='🌱', layout='wide', initial_sidebar_state='expanded')

SITES = {
 'BBO':'Vidullanka PLC','BTO':'Vidullanka PLC','GNT':'Gurugoda Hydro (Pvt) Ltd','WMB':'Vidullanka PLC','MGT':'Vidul Madugheta (Pvt) Ltd','LKM':'Vidullanka PLC','RDP':'Vidullanka PLC','EME':'Nilwala Vidulibala Company (Pvt) Ltd','UDW':'Vidullanka PLC','BRK':'Bhoruka Power Lanka (Pvt) Ltd','MUV':'Muvumbe Hydro (U) Ltd','BKN':'Timex Bukinda Hydro (U) Ltd','MOC':'GEA','KUM':'GEA','ORK':'Orik Corporation (Pvt) Ltd','HRN':'Vidulsolar (Pvt) Ltd','HRN 1':'Vidulsolar (Pvt) Ltd','HRN 2':'Vidulsolar (Pvt) Ltd','MTR':'Vidul Matara Solar Power (Pvt) Ltd','MDP':'Vidulsolar (Pvt) Ltd','DPV':'DPV Solar Energy (Pvt) Ltd','HOF':'Head Office','VPL':'Vidul Power Lanka (Pvt) Ltd','VBL':'Vidul Bio Lanka (Pvt) Ltd'
}
PROGRAMS = ['Daruwanta Diriyak','Ratata Sewanak','Gamata Eliyak','Lowata Aruthak','Vidu Saviya']
CATEGORIES = {
 'Daruwanta Diriyak':['Scholarships','Scholarships for children','School essentials','Children with special needs','School infrastructure development','Sports equipment for schools','Education donations','Other education support'],
 'Ratata Sewanak':['Reforestation','Guide to Deforestation','Plant nursery','Seed planting','Tree planting','Other environmental protection'],
 'Gamata Eliyak':['Donations / Employee Welfare','Community infrastructure','Government institutions / villages','Bridge development','COVID-19 support','Other rural infrastructure'],
 'Lowata Aruthak':['Blood donation camps','Dry rations for employees','Donations for employees','Trash collection','Trash crusher','Robotic nurse','Hospital / medical donations','Other community services'],
 'Vidu Saviya':['Grade 5 Scholarship',"O/L Scholarship",'University Student Scholarship','Special Need Scholarship','One-time payment','Other scholarship payment']
}

@st.cache_resource
def get_engine():
    url=os.getenv('DATABASE_URL') or st.secrets.get('DATABASE_URL','') if hasattr(st,'secrets') else os.getenv('DATABASE_URL','')
    if url:
        if url.startswith('postgres://'): url=url.replace('postgres://','postgresql+psycopg://',1)
        elif url.startswith('postgresql://') and '+psycopg' not in url: url=url.replace('postgresql://','postgresql+psycopg://',1)
        is_postgres = 'postgresql' in url
        return create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5 if is_postgres else 5,
            max_overflow=5 if is_postgres else 0,
            pool_timeout=15,
            pool_recycle=1800,
            connect_args={'sslmode': 'require', 'connect_timeout': 8} if is_postgres else {'check_same_thread': False},
        )
    return create_engine('sqlite:///'+str(BASE/'csr_local.db'), connect_args={'check_same_thread':False}, pool_pre_ping=True)
engine=get_engine()

def run(sql, params=None):
    with engine.begin() as conn: return conn.execute(text(sql),params or {})
def df(sql,params=None):
    with engine.connect() as conn: return pd.read_sql(text(sql),conn,params=params or {})
def hash_pw(pw,salt=None):
    salt=salt or secrets.token_hex(16); digest=hashlib.pbkdf2_hmac('sha256',pw.encode(),salt.encode(),180000).hex(); return salt+'$'+digest
def verify_pw(pw,stored):
    try:
        salt,digest=stored.split('',1);returnhmac.comparedigest(hashpw(pw,salt).split('',1)[1],digest)
    except Exception:return False

@st.cache_resource(show_spinner="Preparing CSR database...")
def init_db():
    pk = 'SERIAL PRIMARY KEY' if engine.dialect.name == 'postgresql' else 'INTEGER PRIMARY KEY'
    stmts=[
    f'''CREATE TABLE IF NOT EXISTS users (id {pk}, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL)''',
    f'''CREATE TABLE IF NOT EXISTS budgets (id {pk}, program TEXT NOT NULL, category TEXT NOT NULL, subcategory TEXT, site TEXT NOT NULL, budget REAL NOT NULL DEFAULT 0, UNIQUE(program,category,subcategory,site))''',
    f'''CREATE TABLE IF NOT EXISTS payments (id {pk}, payment_date TEXT NOT NULL, program TEXT NOT NULL, category TEXT NOT NULL, subcategory TEXT, site TEXT NOT NULL, payment_purpose TEXT NOT NULL, description TEXT, recipient TEXT, amount REAL NOT NULL, payment_type TEXT NOT NULL, bank_name TEXT, bank_branch TEXT, account_holder TEXT, account_number TEXT, reference_no TEXT, status TEXT NOT NULL DEFAULT 'Pending', created_by TEXT NOT NULL, created_at TEXT NOT NULL)''',
    f'''CREATE TABLE IF NOT EXISTS approvals (id {pk}, item_type TEXT NOT NULL, item_id INTEGER NOT NULL, requested_by TEXT NOT NULL, approver TEXT, decision TEXT NOT NULL DEFAULT 'Pending', comments TEXT, decision_date TEXT, created_at TEXT NOT NULL)''',
    f'''CREATE TABLE IF NOT EXISTS nursery (id {pk}, site TEXT NOT NULL, plant_name TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL, UNIQUE(site,plant_name))''',
    f'''CREATE TABLE IF NOT EXISTS planting (id {pk}, site TEXT NOT NULL, planted_date TEXT NOT NULL, location TEXT, plant_name TEXT NOT NULL, quantity INTEGER NOT NULL, source_type TEXT NOT NULL, unit_cost REAL NOT NULL DEFAULT 0, total_cost REAL NOT NULL DEFAULT 0, notes TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL)''',
    f'''CREATE TABLE IF NOT EXISTS scholarships (id {pk}, reference_no TEXT UNIQUE NOT NULL, funding_source TEXT NOT NULL, student_name TEXT NOT NULL, student_id TEXT, school_or_university TEXT, contact TEXT, scholarship_category TEXT NOT NULL, monthly_amount REAL NOT NULL, start_date TEXT NOT NULL, installment_count INTEGER NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL)''',
    f'''CREATE TABLE IF NOT EXISTS scholarship_installments (id {pk}, scholarship_id INTEGER NOT NULL, installment_no INTEGER NOT NULL, due_date TEXT NOT NULL, amount REAL NOT NULL, status TEXT NOT NULL DEFAULT 'Pending', paid_date TEXT, payment_reference TEXT, UNIQUE(scholarship_id,installment_no))'''
    ]
    for s in stmts:
        run(s)

    # Schema migration for older CSR databases. CREATE TABLE IF NOT EXISTS
    # does not add columns to tables that already exist.
    from sqlalchemy import inspect

    # Older versions of the payments table may not have the programme/category
    # fields. The Overview, programme pages, Approvals and Reports all use them.
    # Add missing columns before any page queries run; this is safe for both
    # PostgreSQL and SQLite and preserves all existing payment rows.
    payment_columns = {column['name'] for column in inspect(engine).get_columns('payments')}
    payment_column_definitions = {
        'payment_date': 'TEXT',
        'program': 'TEXT',
        'category': 'TEXT',
        'subcategory': 'TEXT',
        'site': 'TEXT',
        'payment_purpose': 'TEXT',
        'description': 'TEXT',
        'recipient': 'TEXT',
        'amount': 'REAL NOT NULL DEFAULT 0',
        'payment_type': 'TEXT',
        'bank_name': 'TEXT',
        'bank_branch': 'TEXT',
        'account_holder': 'TEXT',
        'account_number': 'TEXT',
        'reference_no': 'TEXT',
        'status': "TEXT NOT NULL DEFAULT 'Pending'",
        'created_by': 'TEXT',
        'created_at': 'TEXT',
    }
    for column_name, column_type in payment_column_definitions.items():
        if column_name not in payment_columns:
            run(f'ALTER TABLE payments ADD COLUMN {column_name} {column_type}')

    # Refresh the column list and populate new fields from legacy fields where
    # possible. Do not overwrite existing programme/category values.
    payment_columns = {column['name'] for column in inspect(engine).get_columns('payments')}
    if 'programme' in payment_columns:
        run("UPDATE payments SET program=programme WHERE (program IS NULL OR TRIM(program)='') AND programme IS NOT NULL")
    if 'csr_program' in payment_columns:
        run("UPDATE payments SET program=csr_program WHERE (program IS NULL OR TRIM(program)='') AND csr_program IS NOT NULL")
    if 'site_code' in payment_columns:
        run("UPDATE payments SET site=site_code WHERE (site IS NULL OR TRIM(site)='') AND site_code IS NOT NULL")
    if 'payment_category' in payment_columns:
        run("UPDATE payments SET category=payment_category WHERE (category IS NULL OR TRIM(category)='') AND payment_category IS NOT NULL")
    if 'payment_purpose' in payment_columns:
        run("UPDATE payments SET category=payment_purpose WHERE (category IS NULL OR TRIM(category)='') AND payment_purpose IS NOT NULL")
    run("UPDATE payments SET program='Vidu Saviya' WHERE program IS NULL OR TRIM(program)=''")
    run("UPDATE payments SET category='Other' WHERE category IS NULL OR TRIM(category)=''")
    run("UPDATE payments SET site='Unknown' WHERE site IS NULL OR TRIM(site)=''")
    run("UPDATE payments SET status='Pending' WHERE status IS NULL OR TRIM(status)=''")

    budget_columns = {column['name'] for column in inspect(engine).get_columns('budgets')}

    # Add the columns expected by this version of the application.
    if 'program' not in budget_columns:
        run('ALTER TABLE budgets ADD COLUMN program TEXT')
    if 'site' not in budget_columns:
        run('ALTER TABLE budgets ADD COLUMN site TEXT')
    if 'budget' not in budget_columns:
        run('ALTER TABLE budgets ADD COLUMN budget REAL NOT NULL DEFAULT 0')

    # Refresh the schema after adding columns, then copy values from common
    # legacy column names without overwriting existing values.
    budget_columns = {column['name'] for column in inspect(engine).get_columns('budgets')}
    if 'site_code' in budget_columns:
        run("UPDATE budgets SET site=site_code WHERE (site IS NULL OR TRIM(site)='') AND site_code IS NOT NULL")
    if 'budget_amount' in budget_columns:
        run('UPDATE budgets SET budget=budget_amount WHERE COALESCE(budget,0)=0 AND budget_amount IS NOT NULL')

    # Map legacy category values to their programme where possible.
    for programme, categories in CATEGORIES.items():
        for category_name in categories:
            run(
                "UPDATE budgets SET program=:program WHERE category=:category AND (program IS NULL OR TRIM(program)=:empty)",
                {'program': programme, 'category': category_name, 'empty': ''}
            )
    run("UPDATE budgets SET program='Vidu Saviya' WHERE program IS NULL OR TRIM(program)=''")
    run("UPDATE budgets SET site='Unknown' WHERE site IS NULL OR TRIM(site)=''")

    if df('SELECT id FROM users WHERE username=:u',{'u':'admin'}).empty:
        run('INSERT INTO users(username,password_hash,role,created_at) VALUES(:u,:p,:r,:d)',{'u':'admin','p':hash_pw('admin@123'),'r':'admin','d':datetime.now().isoformat(timespec='seconds')})
    if df('SELECT id FROM budgets LIMIT 1').empty:
        seed=json.loads((BASE/'budget_seed.json').read_text(encoding='utf8'))
        for x in seed:
            run('INSERT INTO budgets(program,category,subcategory,site,budget) VALUES(:program,:category,:subcategory,:site,:budget)',x)
init_db()

st.markdown('''<style>
:root{--green:#147d43;--deep:#064e3b;--pale:#edf7ef} header[data-testid="stHeader"]{display:none} .stAppViewContainer .main .block-container,.stAppViewBlockContainer{padding-top:0 !important} .stApp{background:#fbfdfb;color:#17352a}.block-container{padding-top:0 !important;max-width:1500px}.sidebar .sidebar-content{background:#f0f7f2}.stButton>button{background:#147d43;color:white;border:1px solid #147d43;border-radius:9px;font-weight:600}.stButton>button:hover{background:#0b6233;color:white;border-color:#0b6233}.metric-card{background:white;border:1px solid #dbe8de;border-radius:14px;padding:17px 19px;box-shadow:0 4px 16px #12331a0a;min-height:142px;height:auto;box-sizing:border-box;display:flex;flex-direction:column;justify-content:flex-start;gap:8px}.metric-card h4,.metric-card h3,.metric-card p{margin-top:0;margin-bottom:4px}.page-banner{background:#eaf5fc;padding:12px 20px;border-radius:0 0 12px 12px;margin:0 0 14px 0}.hero{padding:30px;border-radius:20px;background:linear-gradient(120deg,#effaf1,#ffffff);border:1px solid #d8e8da}.muted{color:#648071}.small{font-size:13px;color:#648071}.login-wrap{padding:22px;border-radius:18px;background:#ffffffdc;border:1px solid #d8e5db}
</style>''',unsafe_allow_html=True)

def money(x): return 'LKR '+format(float(x or 0),',.2f')
def budget_summary(site=None,program=None):
    q='SELECT program,category,site,SUM(budget) budget FROM budgets WHERE 1=1'; p={}
    if site and site!='All sites':q+=' AND site=:site';p['site']=site
    if program and program!='All programmes':q+=' AND program=:program';p['program']=program
    q+=' GROUP BY program,category,site'; b=df(q,p)
    q2="SELECT COALESCE(program,'Vidu Saviya') AS program,COALESCE(category,'Other') AS category,COALESCE(site,'Unknown') AS site,SUM(amount) spent FROM payments WHERE status IN ('Approved','Paid')"; p2={}
    if site and site!='All sites':q2+=' AND site=:site';p2['site']=site
    if program and program!='All programmes':q2+=' AND program=:program';p2['program']=program
    q2 += " AND COALESCE(payment_type,'') NOT LIKE 'Budget addition%'"
    q2+=' GROUP BY COALESCE(program,\'Vidu Saviya\'),COALESCE(category,\'Other\'),COALESCE(site,\'Unknown\')'; spent=df(q2,p2)
    q3="SELECT COALESCE(program,'Vidu Saviya') AS program,COALESCE(category,'Other') AS category,COALESCE(site,'Unknown') AS site,SUM(amount) additions FROM payments WHERE status IN ('Approved','Paid') AND COALESCE(payment_type,'') LIKE 'Budget addition%'"; p3={}
    if site and site!='All sites': q3+=' AND site=:site'; p3['site']=site
    if program and program!='All programmes': q3+=' AND program=:program'; p3['program']=program
    q3+=' GROUP BY COALESCE(program,\'Vidu Saviya\'),COALESCE(category,\'Other\'),COALESCE(site,\'Unknown\')'; additions=df(q3,p3)
    if b.empty:return pd.DataFrame(columns=['program','category','site','budget','additions','spent','unspent'])
    m=b.merge(spent,on=['program','category','site'],how='left').merge(additions,on=['program','category','site'],how='left')
    m['spent']=m.spent.fillna(0); m['additions']=m.additions.fillna(0); m['planned_budget']=m['budget']; m['budget']=m['planned_budget']+m['additions']; m['unspent']=m['budget']-m['spent']; return m

@st.cache_data(show_spinner=False)
def _cached_background_data(path: str, modified_time: float) -> str:
    # Cache image encoding between Streamlit reruns; modified_time invalidates the cache if replaced.
    import base64
    return base64.b64encode(Path(path).read_bytes()).decode('ascii')


def login_page():
    bg=BASE/'assets'/'csr_landscape.png'
    encoded=_cached_background_data(str(bg), bg.stat().st_mtime) if bg.is_file() else ''
    st.markdown(f'''<style>.stApp{{background:linear-gradient(90deg,#ffffff45,#ffffff30),url("data:image/png;base64,{encoded}") center/cover fixed}}</style>''',unsafe_allow_html=True)
    left,right=st.columns([1.08,1],gap='large')
    with left:
        st.markdown('<div class="hero" style="margin-top:0;min-height:310px"><h3>🌱 VIDU SAVIYA</h3><h1 style="font-size:38px;line-height:1.15;color:#064e3b">Investing in People,<br>Communities and Nature</h1><h4>CSR Management and Monitoring System</h4><p>Education · Community development · Reforestation · Sustainability</p></div>',unsafe_allow_html=True)
    with right:
        st.markdown('<div style="height:0"></div>',unsafe_allow_html=True); st.markdown('<div class="login-wrap"><h2>Welcome back</h2><p class="muted">Sign in to your Vidu Saviya account.</p>',unsafe_allow_html=True)
        with st.form('login'):
            u=st.text_input('Username',placeholder='Enter username'); p=st.text_input('Password',type='password',placeholder='Enter password'); go=st.form_submit_button('Sign in',use_container_width=True)
        if go:
            users=df('SELECT username,password_hash,role FROM users WHERE username=:u',{'u':u.strip()})
            if not users.empty and verify_pw(p,users.iloc[0].password_hash): st.session_state.user={'username':u.strip(),'role':users.iloc[0].role};st.rerun()
            else: st.error('Incorrect username or password.')
        with st.expander('Create account'):
            with st.form('create_account'):
                nu=st.text_input('Choose username'); np=st.text_input('Create password',type='password'); np2=st.text_input('Confirm password',type='password'); create=st.form_submit_button('Create account',use_container_width=True)
            if create:
                if not nu.strip() or len(np)<8: st.error('Enter a username and a password with at least 8 characters.')
                elif np!=np2:st.error('Passwords do not match.')
                elif not df('SELECT id FROM users WHERE username=:u',{'u':nu.strip()}).empty:st.error('That username already exists.')
                else:
                    run('INSERT INTO users(username,password_hash,role,created_at) VALUES(:u,:p,:r,:d)',{'u':nu.strip(),'p':hash_pw(np),'r':'user','d':datetime.now().isoformat(timespec='seconds')});st.success('Account created. Sign in with your new credentials.')
        st.markdown('</div>',unsafe_allow_html=True)

if 'user' not in st.session_state:
    login_page(); st.stop()
user=st.session_state.user
with st.sidebar:
    st.markdown('## 🌱 Vidu Saviya');st.caption(f"Signed in as **{user['username']}** · {user['role']}")
    page=st.radio('Navigation',['Overview','Daruwanta Diriyak','Ratata Sewanak','Gamata Eliyak','Lowata Aruthak','Vidu Saviya','Approvals','CSR Database','Reforestation & Nursery','Reports'],label_visibility='visible')
    st.divider()
    if st.button('Sign out',use_container_width=True):st.session_state.pop('user',None);st.rerun()

st.markdown(f'<div class="page-banner" style="display:flex;justify-content:space-between;align-items:center"><div><div class="small">VIDULLANKA PLC · CSR BUDGET PLAN 2026–2027</div><h1 style="margin:0;color:#064e3b">{page}</h1></div><div style="font-size:34px">🌿</div></div>',unsafe_allow_html=True)
st.write('')

site_options=['All sites']+sorted(SITES.keys())
if page=='Overview':
    site=st.selectbox('Filter by power plant / site',site_options,key='ov_site'); summaries=budget_summary(site)
    total_budget=summaries.budget.sum() if not summaries.empty else 0; total_spent=summaries.spent.sum() if not summaries.empty else 0; total_unspent=summaries.unspent.sum() if not summaries.empty else 0
    overview_counts = df("SELECT \
        (SELECT COUNT(*) FROM approvals WHERE decision='Pending') AS pending, \
        (SELECT COALESCE(SUM(quantity),0) FROM planting WHERE (:site='All sites' OR site=:site)) AS planted, \
        (SELECT COALESCE(SUM(quantity),0) FROM nursery WHERE (:site='All sites' OR site=:site)) AS nursery_count, \
        (SELECT COUNT(*) FROM payments WHERE (:site='All sites' OR site=:site)) AS payment_count", {'site': site})
    count_row = overview_counts.iloc[0]
    pending = int(count_row['pending'] or 0)
    planted = int(count_row['planted'] or 0)
    cols=st.columns(4)
    for col,label,val in zip(cols,['Approved / planned budget','Approved & paid spend','Unspent budget','Pending approvals'],[money(total_budget),money(total_spent),money(total_unspent),str(pending)]):
        col.markdown(f'<div class="metric-card"><div class="small">{label}</div><h3>{val}</h3></div>',unsafe_allow_html=True)
    st.write(''); st.subheader('Programme summaries')
    if summaries.empty: st.info('Budget data has not been loaded yet.')
    else:
        psummary=summaries.groupby('program',as_index=False)[['budget','spent','unspent']].sum()
        cards=st.columns(2)
        for i,(_,r) in enumerate(psummary.iterrows()):
            with cards[i%2]:st.markdown(f'<div class="metric-card"><h4>{r.program}</h4><p>Budget: <b>{money(r.budget)}</b></p><p>Spent: {money(r.spent)}</p><p>Unspent: <b>{money(r.unspent)}</b></p></div>',unsafe_allow_html=True)
        st.write('')  # Keep a clear gap after programme summary cards.
        st.subheader('Budget by category'); st.dataframe(summaries.groupby(['program','category'],as_index=False)[['budget','spent','unspent']].sum().style.format({'budget':'{:,.2f}','spent':'{:,.2f}','unspent':'{:,.2f}'}),use_container_width=True,hide_index=True)
    st.subheader('Reforestation overview')
    n1,n2,n3=st.columns(3);n1.metric('Total plants / seeds planted',f'{planted:,}');n2.metric('Plants currently in nursery',f"{int(count_row['nursery_count'] or 0):,}");n3.metric('Payment requests',int(count_row['payment_count'] or 0))
    source_totals = df("SELECT source_type, COALESCE(SUM(quantity),0) AS quantity FROM planting WHERE (:site='All sites' OR site=:site) GROUP BY source_type ORDER BY source_type", {'site': site})
    if not source_totals.empty:
        st.subheader('Plants planted by source')
        st.dataframe(source_totals.rename(columns={'source_type':'Planting source','quantity':'Total plants / seeds'}), use_container_width=True, hide_index=True)
    st.caption('Budget seed values were imported from the supplied CSR BP 2026–2027 workbook. Spend is counted only after a payment is approved or marked Paid. Nursery stock is the current remaining quantity; planting records include nursery plants, seed planting, purchased plants and donated plants.')
elif page in PROGRAMS or page in ['Daruwanta Diriyak','Ratata Sewanak','Gamata Eliyak','Lowata Aruthak','Vidu Saviya']:
    prog=page; site=st.selectbox('Power plant / site',site_options[1:],key='program_site_'+prog)
    cat_opts=CATEGORIES[prog]
    summ=budget_summary(site,prog); st.caption(f'Budget, spend and unspent amount for {prog} · {SITES.get(site,site)}')
    if not summ.empty:
        s=summ.groupby('category',as_index=False)[['budget','spent','unspent']].sum();st.dataframe(s.style.format({'budget':'LKR {:,.2f}','spent':'LKR {:,.2f}','unspent':'LKR {:,.2f}'}),use_container_width=True,hide_index=True)
    if prog == 'Daruwanta Diriyak':
        payment_tab, one_time_tab = st.tabs(['Payments / expenses', 'One-time payment'])
    else:
        payment_tab = st.container()
        one_time_tab = None
    with payment_tab:
        st.subheader('Record a payment / expense')
        with st.form('expense_'+prog):
            c1,c2,c3=st.columns(3); category=c1.selectbox('Category',cat_opts); purpose=c2.selectbox('Payment purpose',cat_opts); amount=c3.number_input('Amount (LKR)',min_value=0.0,step=500.0)
            c4,c5,c6=st.columns(3); pdate=c4.date_input('Payment date',date.today()); payment_type=c5.selectbox('Payment type',['Bank transfer','Cash','Cheque','One-time payment','Scholarship']); recipient=c6.text_input('Recipient / payee')
            desc=st.text_input('Description / reason'); subcat=st.text_input('Subcategory / detail (optional)'); bank=st.text_input('Bank name'); branch=st.text_input('Bank branch'); holder=st.text_input('Account holder'); account=st.text_input('Account number'); ref=st.text_input('Reference / voucher no.')
            submit=st.form_submit_button('Submit for approval')
        if submit:
            if amount<=0:st.error('Amount must be greater than zero.')
            else:
                res=run('INSERT INTO payments(payment_date,program,category,subcategory,site,payment_purpose,description,recipient,amount,payment_type,bank_name,bank_branch,account_holder,account_number,reference_no,status,created_by,created_at) VALUES(:d,:p,:c,:sc,:s,:purpose,:desc,:rec,:a,:pt,:bank,:branch,:holder,:acct,:ref,:status,:by,:now)',{'d':pdate.isoformat(),'p':prog,'c':category,'sc':subcat,'s':site,'purpose':purpose,'desc':desc,'rec':recipient,'a':amount,'pt':payment_type,'bank':bank,'branch':branch,'holder':holder,'acct':account,'ref':ref,'status':'Pending','by':user['username'],'now':datetime.now().isoformat(timespec='seconds')})
                pid=int(df('SELECT MAX(id) id FROM payments').iloc[0].id);run('INSERT INTO approvals(item_type,item_id,requested_by,decision,created_at) VALUES(:t,:i,:u,:d,:now)',{'t':'payment','i':pid,'u':user['username'],'d':'Pending','now':datetime.now().isoformat(timespec='seconds')});st.success('Payment saved and sent to Approvals.');st.rerun()
        st.subheader('Payment history'); history=df('SELECT payment_date,category,payment_purpose,recipient,amount,payment_type,status,reference_no FROM payments WHERE program=:p AND site=:s ORDER BY payment_date DESC',{'p':prog,'s':site})
        st.dataframe(history.style.format({'amount':'LKR {:,.2f}'}),use_container_width=True,hide_index=True)
        st.subheader('How the category budget has been used')
        category_budget = summ[['category','budget','spent','unspent']].copy() if not summ.empty else pd.DataFrame(columns=['category','budget','spent','unspent'])
        if not category_budget.empty:
            category_budget['Budget calculation'] = category_budget.apply(lambda r: f"{money(r['budget'])} budget − {money(r['spent'])} approved / paid expenses = {money(r['unspent'])} unspent", axis=1)
            st.dataframe(category_budget[['category','budget','spent','unspent','Budget calculation']].style.format({'budget':'LKR {:,.2f}','spent':'LKR {:,.2f}','unspent':'LKR {:,.2f}'}),use_container_width=True,hide_index=True)
        st.caption('The remaining budget is calculated from the existing category budget plus approved incoming funds, minus expenses marked Approved or Paid. Pending and rejected expenses are listed in the payment history but do not reduce the available budget.')

    if prog == 'Daruwanta Diriyak' and one_time_tab is not None:
        with one_time_tab:
            st.subheader('Record a one-time payment')
            with st.form('daruwanta_one_time'):
                c1,c2=st.columns(2); one_cat=c1.selectbox('Category',cat_opts,key='dt_one_cat'); one_site=c2.selectbox('Site',sorted(SITES),index=sorted(SITES).index(site),key='dt_one_site')
                one_amount=st.number_input('Amount (LKR)',min_value=0.0,step=500.0,key='dt_one_amount'); one_date=st.date_input('Payment date',date.today(),key='dt_one_date')
                one_recipient=st.text_input('Recipient / payee',key='dt_one_recipient'); one_purpose=st.text_input('Purpose / explanation',key='dt_one_purpose')
                one_type=st.selectbox('Payment type',['Bank transfer','Cash','Cheque'],key='dt_one_type'); one_bank=st.text_input('Bank name',key='dt_one_bank'); one_branch=st.text_input('Bank branch',key='dt_one_branch')
                one_holder=st.text_input('Account holder',key='dt_one_holder'); one_account=st.text_input('Account number',key='dt_one_account'); one_ref=st.text_input('Reference / voucher no.',key='dt_one_ref')
                one_submit=st.form_submit_button('Submit one-time payment')
            if one_submit:
                if one_amount <= 0: st.error('Amount must be greater than zero.')
                else:
                    run('INSERT INTO payments(payment_date,program,category,site,payment_purpose,description,recipient,amount,payment_type,bank_name,bank_branch,account_holder,account_number,reference_no,status,created_by,created_at) VALUES(:d,:p,:c,:s,:pu,:de,:r,:a,:pt,:b,:br,:h,:ac,:ref,:st,:u,:now)', {'d':one_date.isoformat(),'p':prog,'c':one_cat,'s':one_site,'pu':one_purpose or one_cat,'de':one_purpose,'r':one_recipient,'a':one_amount,'pt':'One-time payment - '+one_type,'b':one_bank,'br':one_branch,'h':one_holder,'ac':one_account,'ref':one_ref,'st':'Pending','u':user['username'],'now':datetime.now().isoformat(timespec='seconds')})
                    pid=int(df('SELECT MAX(id) id FROM payments').iloc[0].id); run('INSERT INTO approvals(item_type,item_id,requested_by,decision,created_at) VALUES(:t,:i,:u,:d,:now)', {'t':'payment','i':pid,'u':user['username'],'d':'Pending','now':datetime.now().isoformat(timespec='seconds')})
                    st.success('One-time payment submitted for approval.'); st.rerun()

    if prog == 'Vidu Saviya':
        st.divider()
        st.subheader('Scholarship register and monthly payments')
        st.caption('April and August are excluded from the payment schedule. Each scholarship is registered separately, so one student can have more than one reference number.')
        funding_options = ['Vidullanka', 'Other companies', 'Vidul Biomass and Vidul Plantation']
        scholarship_categories = ['Grade 5 Scholarship', "O/L passed with 9A's", 'University Selection']
        category_meta = {'Grade 5 Scholarship': ('VLL-SH', 3000.0, 60), "O/L passed with 9A's": ('VLL-OL', 3500.0, 20), 'University Selection': ('VLL-UN', 3500.0, 40)}
        with st.form('scholarship_register_form'):
            a,b,c = st.columns(3)
            funding_source = a.selectbox('Scholarship funding source', funding_options)
            scholarship_category = b.selectbox('Scholarship category', scholarship_categories)
            student_name = c.text_input('Student full name')
            d,e,f = st.columns(3)
            student_id = d.text_input('Student ID / NIC (optional)')
            institution = e.text_input('School / university')
            contact = f.text_input('Contact number (optional)')
            start_date = st.date_input('First eligible payment month', date.today().replace(day=1))
            monthly_amount = st.number_input('Monthly payment (LKR)', min_value=0.0, step=500.0, value=category_meta[scholarship_category][1])
            register = st.form_submit_button('Register scholarship')
        if register:
            if not student_name.strip():
                st.error('Enter the student full name.')
            elif monthly_amount <= 0:
                st.error('Monthly payment must be greater than zero.')
            else:
                prefix, default_amount, installment_count = category_meta[scholarship_category]
                existing = df('SELECT reference_no FROM scholarships WHERE reference_no LIKE :prefix', {'prefix': prefix+'-%'})
                nums = []
                for value in existing.get('reference_no', pd.Series(dtype=str)).astype(str):
                    try: nums.append(int(value.rsplit('-',1)[1]))
                    except Exception: pass
                reference_no = f'{prefix}-{(max(nums) if nums else 0)+1:03d}'
                run('INSERT INTO scholarships(reference_no,funding_source,student_name,student_id,school_or_university,contact,scholarship_category,monthly_amount,start_date,installment_count,created_by,created_at) VALUES(:ref,:fund,:name,:sid,:inst,:contact,:cat,:amount,:start,:count,:user,:now)',
                    {'ref':reference_no,'fund':funding_source,'name':student_name.strip(),'sid':student_id.strip(),'inst':institution.strip(),'contact':contact.strip(),'cat':scholarship_category,'amount':float(monthly_amount),'start':start_date.isoformat(),'count':installment_count,'user':user['username'],'now':datetime.now().isoformat(timespec='seconds')})
                scholarship_id = int(df('SELECT id FROM scholarships WHERE reference_no=:ref', {'ref':reference_no}).iloc[0].id)
                yy, mm, created = start_date.year, start_date.month, 0
                while created < installment_count:
                    if mm not in (4, 8):
                        run('INSERT INTO scholarship_installments(scholarship_id,installment_no,due_date,amount,status) VALUES(:sid,:no,:due,:amount,:status)',
                            {'sid':scholarship_id,'no':created+1,'due':date(yy,mm,1).isoformat(),'amount':float(monthly_amount),'status':'Pending'})
                        created += 1
                    mm += 1
                    if mm > 12: mm = 1; yy += 1
                st.success(f'Scholarship registered: {reference_no}. {installment_count} scheduled payments created.')
                st.rerun()
        scholarships = df('SELECT id,reference_no,funding_source,student_name,student_id,school_or_university,scholarship_category,monthly_amount,start_date,installment_count FROM scholarships ORDER BY funding_source,student_name')
        st.subheader('Scholarship records')
        if scholarships.empty:
            st.info('No scholarships have been registered yet.')
        else:
            for idx, source_name in enumerate(funding_options, start=1):
                source_rows = scholarships[scholarships.funding_source == source_name]
                if not source_rows.empty:
                    st.markdown(f'**{source_name}**')
                    st.dataframe(source_rows.drop(columns=['id']), use_container_width=True, hide_index=True)
            chosen_ref = st.selectbox('Select scholarship reference', scholarships.reference_no.tolist(), key='scholarship_selected_ref')
            selected_scholarship = scholarships[scholarships.reference_no == chosen_ref].iloc[0]
            installments = df('SELECT installment_no,due_date,amount,status,paid_date,payment_reference FROM scholarship_installments WHERE scholarship_id=:sid ORDER BY installment_no', {'sid':int(selected_scholarship.id)})
            st.subheader(f'Payment schedule · {chosen_ref}')
            st.dataframe(installments.style.format({'amount':'LKR {:,.2f}'}), use_container_width=True, hide_index=True)
            pending_installments = installments[installments.status == 'Pending']
            if not pending_installments.empty:
                with st.form('scholarship_installment_paid'):
                    opts = [f"#{int(r.installment_no)} · {r.due_date} · {money(r.amount)}" for _,r in pending_installments.iterrows()]
                    selected_installment = st.selectbox('Mark installment as paid', opts)
                    paid_date = st.date_input('Actual payment date', date.today())
                    payment_reference = st.text_input('Payment / voucher reference')
                    mark_paid = st.form_submit_button('Record scholarship payment')
                if mark_paid:
                    ix = opts.index(selected_installment)
                    installment_no = int(pending_installments.iloc[ix].installment_no)
                    installment_amount = float(pending_installments.iloc[ix].amount)
                    run("UPDATE scholarship_installments SET status='Paid',paid_date=:paid,payment_reference=:ref WHERE scholarship_id=:sid AND installment_no=:no",
                        {'paid':paid_date.isoformat(),'ref':payment_reference.strip(),'sid':int(selected_scholarship.id),'no':installment_no})
                    run('INSERT INTO payments(payment_date,program,category,subcategory,site,payment_purpose,description,recipient,amount,payment_type,reference_no,status,created_by,created_at) VALUES(:d,:p,:c,:sc,:site,:purpose,:desc,:recipient,:amount,:type,:ref,:status,:user,:now)',
                        {'d':paid_date.isoformat(),'p':'Vidu Saviya','c':selected_scholarship.scholarship_category,'sc':chosen_ref,'site':'Unknown','purpose':'Scholarship installment','desc':f"Installment #{installment_no} · {selected_scholarship.funding_source}",'recipient':selected_scholarship.student_name,'amount':installment_amount,'type':'Scholarship','ref':payment_reference.strip() or chosen_ref,'status':'Paid','user':user['username'],'now':datetime.now().isoformat(timespec='seconds')})
                    st.success('Scholarship payment recorded.')
                    st.rerun()
            output_sch = BytesIO()
            with pd.ExcelWriter(output_sch, engine='openpyxl') as writer:
                for idx, source_name in enumerate(funding_options, start=1):
                    scholarships[scholarships.funding_source == source_name].drop(columns=['id']).to_excel(writer, index=False, sheet_name=f'Scholarships {idx}')
                all_schedule = df('SELECT s.reference_no,s.funding_source,s.student_name,s.student_id,s.school_or_university,s.scholarship_category,i.installment_no,i.due_date,i.amount,i.status,i.paid_date,i.payment_reference FROM scholarships s JOIN scholarship_installments i ON i.scholarship_id=s.id ORDER BY s.funding_source,s.student_name,i.installment_no')
                all_schedule.to_excel(writer, index=False, sheet_name='Payment Schedule')
            st.download_button('Download scholarship workbook (3 sheets + schedule)', output_sch.getvalue(), file_name='vidu_saviya_scholarships.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

elif page=='Approvals':
    st.subheader('Approval requests'); req=df("SELECT a.id approval_id,a.item_type,a.item_id,a.requested_by,a.decision,a.comments,a.created_at,p.program,p.category,p.site,p.payment_purpose,p.recipient,p.amount,p.payment_type,p.status FROM approvals a LEFT JOIN payments p ON a.item_type='payment' AND p.id=a.item_id ORDER BY a.created_at DESC")
    if req.empty:st.info('There are no approval requests yet.')
    else:
        st.dataframe(req.drop(columns=['comments']),use_container_width=True,hide_index=True)
        pending=req[req.decision=='Pending']
        if not pending.empty:
            labels=[f"#{int(r.approval_id)} · {r.item_type} · {r.program or ''} · {r.site or ''} · {money(r.amount)}" for _,r in pending.iterrows()]; choice=st.selectbox('Select approval request',labels); selected=pending.iloc[labels.index(choice)]
            with st.form('decision'):
                st.text_input('Your full name',value=user['username']);decision=st.radio('Decision',['Approve','Reject'],horizontal=True);comments=st.text_area('Comments');confirm=st.checkbox('I confirm this decision is mine.');submit=st.form_submit_button('Submit decision')
            if submit:
                if not confirm:st.error('Please confirm the decision.')
                elif user['role']!='admin':st.error('Only an admin can approve or reject requests in this starter configuration.')
                else:
                    new='Approved' if decision=='Approve' else 'Rejected';run('UPDATE approvals SET approver=:u,decision=:d,comments=:c,decision_date=:t WHERE id=:id',{'u':user['username'],'d':new,'c':comments,'t':datetime.now().isoformat(timespec='seconds'),'id':int(selected.approval_id)})
                    if selected.item_type=='payment':run('UPDATE payments SET status=:s WHERE id=:id',{'s':new,'id':int(selected.item_id)})
                    st.success('Decision recorded.');st.rerun()
elif page=='CSR Database':
    st.subheader('CSR Database · Review and approval status'); kind=st.selectbox('Database view',['Payments','Budgets','Approvals','Users'])
    if kind=='Payments': data=df('SELECT * FROM payments ORDER BY created_at DESC')
    elif kind=='Budgets':data=df('SELECT * FROM budgets ORDER BY program,category,site')
    elif kind=='Approvals':data=df('SELECT * FROM approvals ORDER BY created_at DESC')
    else:data=df('SELECT id,username,role,created_at FROM users ORDER BY username') if user['role']=='admin' else pd.DataFrame({'Notice':['Only admin users can view account records.']})
    st.dataframe(data,use_container_width=True,hide_index=True)
    if kind=='Budgets' and user['role']=='admin' and not data.empty:
        st.caption('Edit a budget by entering its ID and revised amount.')
        with st.form('edit_budget'):
            bid=st.number_input('Budget row ID',min_value=1,step=1);newamount=st.number_input('Revised budget (LKR)',min_value=0.0,step=1000.0);ok=st.form_submit_button('Update budget')
        if ok:run('UPDATE budgets SET budget=:b WHERE id=:id',{'b':newamount,'id':int(bid)});st.success('Budget updated.');st.rerun()
elif page=='Reforestation & Nursery':
    st.subheader('Reforestation · Nursery and planting'); st.caption('Only plants marked “Taken from nursery” reduce nursery stock. Plants sourced outside are added to trees planted without reducing nursery stock. Associated costs are recorded against Ratata Sewanak → Reforestation and reduce the available budget only after approval/payment.')
    with st.form('nursery_add'):
        c1,c2,c3,c4=st.columns(4);ns=c1.selectbox('Site',sorted(SITES));pn=c2.text_input('Plant / species name');qty=c3.number_input('Quantity to add / set',min_value=0,step=1);stock_action=c4.selectbox('Stock action',['Add quantity to nursery','Set total nursery quantity']);save=st.form_submit_button('Save nursery stock')
    if save and pn.strip():
        old=df('SELECT id,quantity FROM nursery WHERE site=:s AND plant_name=:p',{'s':ns,'p':pn.strip()})
        if old.empty:run('INSERT INTO nursery(site,plant_name,quantity,updated_at,updated_by) VALUES(:s,:p,:q,:t,:u)',{'s':ns,'p':pn.strip(),'q':int(qty),'t':datetime.now().isoformat(timespec='seconds'),'u':user['username']})
        else:
            new_qty=int(qty) if stock_action=='Set total nursery quantity' else int(old.iloc[0].quantity)+int(qty)
            run('UPDATE nursery SET quantity=:q,updated_at=:t,updated_by=:u WHERE site=:s AND plant_name=:p',{'q':new_qty,'t':datetime.now().isoformat(timespec='seconds'),'u':user['username'],'s':ns,'p':pn.strip()})
        st.success('Nursery stock updated. Added quantities increase the existing stock; plants taken from the nursery are deducted when a planting record is saved.');st.rerun()
    inventory=df('SELECT site,plant_name,quantity,updated_at,updated_by FROM nursery ORDER BY site,plant_name');st.dataframe(inventory,use_container_width=True,hide_index=True)
    st.metric('Total plants currently in nursery', f"{int(inventory['quantity'].sum()) if not inventory.empty else 0:,}")
    st.subheader('Record seed planting or tree planting')
    with st.form('planting'):
        c1,c2,c3=st.columns(3);ps=c1.selectbox('Site',sorted(SITES),key='plant_site');pdte=c2.date_input('Planting date',date.today());loc=c3.text_input('Location')
        c4,c5,c6=st.columns(3);species=c4.text_input('Plant / species');quantity=c5.number_input('Number of plants / seeds',min_value=1,step=1);source=c6.selectbox('Source',['Taken from nursery','Seed planted','Purchased plants','Donated plants','Taken from outside / donated externally','Other'])
        c7,c8=st.columns(2);cost=c7.number_input('Cost per plant / seed (LKR)',min_value=0.0,step=10.0);notes=c8.text_input('Notes');saveplant=st.form_submit_button('Record planting')
    if saveplant:
        total=float(quantity)*float(cost)
        can_save=True
        if source=='Taken from nursery':
            stock=df('SELECT quantity FROM nursery WHERE site=:s AND plant_name=:p',{'s':ps,'p':species.strip()})
            if stock.empty or int(stock.iloc[0].quantity)<quantity:
                st.error('Nursery stock is missing or insufficient. Update nursery inventory first.'); can_save=False
            else:
                run('UPDATE nursery SET quantity=quantity-:q,updated_at=:t,updated_by=:u WHERE site=:s AND plant_name=:p',{'q':int(quantity),'t':datetime.now().isoformat(timespec='seconds'),'u':user['username'],'s':ps,'p':species.strip()})
        if can_save:
            run('INSERT INTO planting(site,planted_date,location,plant_name,quantity,source_type,unit_cost,total_cost,notes,created_by,created_at) VALUES(:s,:d,:l,:p,:q,:src,:cost,:total,:n,:u,:t)',{'s':ps,'d':pdte.isoformat(),'l':loc,'p':species.strip(),'q':int(quantity),'src':source,'cost':cost,'total':total,'n':notes,'u':user['username'],'t':datetime.now().isoformat(timespec='seconds')})
            if total>0:
                run('INSERT INTO payments(payment_date,program,category,subcategory,site,payment_purpose,description,amount,payment_type,status,created_by,created_at) VALUES(:d,:p,:c,:sc,:s,:pu,:de,:a,:pt,:st,:u,:t)',{'d':pdte.isoformat(),'p':'Ratata Sewanak','c':'Reforestation','sc':source,'s':ps,'pu':'Tree / seed planting','de':f'{quantity} × {species} ({source})','a':total,'pt':'Reforestation cost','st':'Pending','u':user['username'],'t':datetime.now().isoformat(timespec='seconds')});pid=int(df('SELECT MAX(id) id FROM payments').iloc[0].id);run('INSERT INTO approvals(item_type,item_id,requested_by,decision,created_at) VALUES(:t,:i,:u,:d,:now)',{'t':'payment','i':pid,'u':user['username'],'d':'Pending','now':datetime.now().isoformat(timespec='seconds')})
            st.success('Planting record saved. Associated cost was added as a pending payment for approval.');st.rerun()
    planted=df('SELECT site,planted_date,location,plant_name,quantity,source_type,unit_cost,total_cost,notes FROM planting ORDER BY planted_date DESC');st.subheader('Planting records');st.dataframe(planted.style.format({'unit_cost':'LKR {:,.2f}','total_cost':'LKR {:,.2f}'}),use_container_width=True,hide_index=True)
    if not planted.empty:
        st.subheader('Total plants / seeds planted by source')
        planted_by_source=planted.groupby('source_type',as_index=False)['quantity'].sum().rename(columns={'source_type':'Planting source','quantity':'Total plants / seeds planted'})
        st.dataframe(planted_by_source,use_container_width=True,hide_index=True)
        st.metric('Total plants / seeds planted', f"{int(planted['quantity'].sum()):,}")
elif page=='Reports':
    st.subheader('CSR reports and exports')
    with st.expander('Record incoming funds / budget addition'):
        with st.form('budget_addition_form'):
            add1,add2,add3=st.columns(3); add_prog=add1.selectbox('Programme receiving funds',PROGRAMS); add_cat=add2.selectbox('Category receiving funds',sorted({c for values in CATEGORIES.values() for c in values}),key='add_funds_category')
            add_site=add3.selectbox('Site receiving funds',sorted(SITES)); add_amount=st.number_input('Funds received (LKR)',min_value=0.0,step=1000.0); add_date=st.date_input('Date received',date.today()); add_source=st.text_input('Source / reference / explanation'); add_submit=st.form_submit_button('Record incoming funds')
        if add_submit:
            if add_amount<=0: st.error('Funds received must be greater than zero.')
            else:
                run('INSERT INTO payments(payment_date,program,category,site,payment_purpose,description,amount,payment_type,status,created_by,created_at) VALUES(:d,:p,:c,:s,:pu,:de,:a,:pt,:st,:u,:now)', {'d':add_date.isoformat(),'p':add_prog,'c':add_cat,'s':add_site,'pu':'Budget addition / funds received','de':add_source,'a':add_amount,'pt':'Budget addition / funds received','st':'Approved','u':user['username'],'now':datetime.now().isoformat(timespec='seconds')})
                st.success('Incoming funds recorded and added to the relevant category budget.'); st.rerun()
    site=st.selectbox('Site filter',site_options,key='report_site');prog=st.selectbox('Programme filter',['All programmes']+PROGRAMS,key='report_prog');summary=budget_summary(site,prog)
    if not summary.empty:
        st.dataframe(summary.style.format({'budget':'LKR {:,.2f}','spent':'LKR {:,.2f}','unspent':'LKR {:,.2f}'}),use_container_width=True,hide_index=True)
        st.caption('Budget reconciliation: planned budget + separately recorded budget additions − approved/paid expenses = available balance. Pending and rejected payments do not reduce the available balance.')
        st.download_button('Download budget summary CSV',summary.to_csv(index=False).encode('utf-8'),file_name='csr_budget_summary.csv',mime='text/csv')
    payments=df('SELECT * FROM payments WHERE (:site=\'All sites\' OR site=:site) AND (:prog=\'All programmes\' OR program=:prog) ORDER BY payment_date DESC',{'site':site,'prog':prog})
    st.subheader('Payments report');st.dataframe(payments,use_container_width=True,hide_index=True);st.download_button('Download payments CSV',payments.to_csv(index=False).encode('utf-8'),file_name='csr_payments.csv',mime='text/csv')
    plants=df('SELECT * FROM planting WHERE (:site=\'All sites\' OR site=:site) ORDER BY planted_date DESC',{'site':site});st.subheader('Reforestation report');st.dataframe(plants,use_container_width=True,hide_index=True);st.download_button('Download planting CSV',plants.to_csv(index=False).encode('utf-8'),file_name='csr_planting.csv',mime='text/csv')
    # Excel workbook documents the budget calculation and the exact planting source/location.
    excel_summary=summary.copy()
    if not excel_summary.empty:
        excel_summary['Planned budget (LKR)']=excel_summary.get('planned_budget', excel_summary['budget'])
        excel_summary['Incoming funds added (LKR)']=excel_summary['additions']
        excel_summary['Approved / paid expenses (LKR)']=excel_summary['spent']
        excel_summary['Available budget after expenses (LKR)']=excel_summary['unspent']
        excel_summary['Calculation']='Planned budget + approved incoming funds - approved/paid expenses; pending/rejected expenses excluded'
    try:
        output=BytesIO()
        with pd.ExcelWriter(output,engine='openpyxl') as writer:
            (excel_summary if not excel_summary.empty else summary).to_excel(writer,index=False,sheet_name='Budget reconciliation')
            payments.to_excel(writer,index=False,sheet_name='Payment ledger')
            plants.to_excel(writer,index=False,sheet_name='Reforestation source and cost')
        st.download_button('Download complete CSR Excel report',output.getvalue(),file_name='vidu_saviya_csr_report.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as exc:
        st.warning(f'Excel export is unavailable until openpyxl is installed: {exc}')

st.divider();st.caption('Vidu Saviya CSR Management · Budget plan 2026–2027 · Store bank account information only in a properly access-controlled deployment.')


