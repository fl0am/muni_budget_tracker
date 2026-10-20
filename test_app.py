from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=60).run()
assert not at.exception, at.exception
print("metrics:", [(m.label, m.value) for m in at.metric])
print("rows in call list:", len(at.dataframe[0].value))
print(at.dataframe[0].value.head(5).to_string())
# all states, October
at.sidebar.multiselect[0].set_value([]).run()
assert not at.exception, at.exception
print("US metrics:", [(m.label, m.value) for m in at.metric])
at.sidebar.selectbox[0].set_value("March").run()
assert not at.exception
print("US March:", [(m.label, m.value) for m in at.metric])
# Lookup tab
at.sidebar.multiselect[0].set_value(["GA"]).run()
lk = [s for s in at.selectbox if s.label == "Government"][0]
lk.set_value(next(o for o in lk.options if o.startswith("Atlanta City"))).run()
assert not at.exception, at.exception
print("lookup metrics:", [(m.label, m.value) for m in at.metric][-2:])
print("ALL TESTS PASSED")
