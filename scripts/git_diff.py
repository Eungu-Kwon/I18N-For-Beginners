import sys
import git_info
import yaml
import subprocess
import os
from datetime import datetime
from jinja2 import Template
from collections import defaultdict

from translate import Translate

def dtree(): return defaultdict(dtree)

def get_leaf(t, where):
	for i in where:
		t = t[i]
	return t

def get_diff(commit1, commit2, file_name, by_tree=True):
	state = file_name['state']

	cur_name = file_name['name'].split('/')[-1]
	info = None
	word_count = (-1, -1)

	exist = git_info.is_exist(commit2, file_name['name'])
	doc_words = 0

	if by_tree:
		out = subprocess.check_output(['git', 'diff', commit1, commit2, '--word-diff', '--', file_name['name']], encoding='utf-8').splitlines()
		
		if state == 'M':
			if exist:
				word_count, info = git_info.get_modified_info(out, by_tree)
				doc_words = git_info.get_git_word_count(commit1, file_name['name'])

				info['original_words'] = git_info.get_git_word_count(commit2, file_name['name'])
				info['translate_words'] = git_info.get_git_word_count(commit2, file_name['name'])
				info['mod_rate'] = round((info['added'] + info['erased']) / (info['translate_words'] + info['original_words']) * 100, 2)
				info['trans_rate'] = round(info['translated'] / info['original_words'] * 100, 2)
			state = 'Modified'
		elif state == 'A':
			doc_words = git_info.get_git_word_count(commit2, file_name['name'])
			word_count = (doc_words, 0)
			state = 'Added'
		elif state == 'R':
			cur_name = file_name['newname'].split('/')[-1]
			doc_words = git_info.get_git_word_count(commit2, file_name['newname'])
			state = 'Renamed'
		elif state == 'D':
			state = 'Deleted'
	else:
		t_path = get_translated_file(file_name['name'])
		if t_path != None:
			out, err = subprocess.Popen(['git', 'diff', '--no-index', '--word-diff', '--', t_path, file_name['name']], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8').communicate()

			out = out.splitlines()
			word_count, info = git_info.get_modified_info(out, by_tree)
			doc_words = git_info.get_git_word_count(commit1, file_name['name'])

			info['original_words'] = git_info.get_git_word_count(commit1, file_name['name'])
			info['translate_words'] = git_info.get_git_word_count(commit1, file_name['name'])
			info['mod_rate'] = round((info['added'] + info['erased']) / (info['translate_words'] + info['original_words']) * 100, 2)
			info['trans_rate'] = round(info['translated'] / info['original_words'] * 100, 2)

	return {'mod': True,
		'dir': file_name['name'],
		'name': file_name['name'].split('/')[-1],
		'new_name': cur_name,
		'word_count': word_count,
		'doc_words': doc_words,
		'state': state,
		'info': info}

def preorder(t, li, depth = 0):
	for k, v in t.items():
		if k != '/data/':
			li.append({'level': depth, 'data': k, 'is_leaf': False})
			preorder(t[k], li, depth + 1)
		else:
			li.pop()
			li.append({'level': depth-1, 'data': v, 'is_leaf': True})

def render_page(title, tree, c1, c2, md_file, stat, by_tree=True):
	tree_list = []
	remotes = {}
	for i in git_info.get_remote():
		remotes[i[1]] = i[0]

	trans_list = git_info.get_files(c1)
	trans_list = [x for x in trans_list if not is_untracking_file(c1, x)]

	origin_info = {}
	if by_tree:
		orig_list = git_info.get_files(c2)
		orig_list = [x for x in orig_list if not is_untracking_file(c2, x)]
		origin_info = {'commit': git_info.get_commit_str(c2),
				'date': git_info.get_commit_date(c2),
				'file_num': len(orig_list),
				'url': remotes['upstream']}

	trans_info = {'commit': git_info.get_commit_str(c1),
			'date': git_info.get_commit_date(c1),
			'file_num': len(trans_list),
			'url': remotes['origin']}
	
	preorder(tree, tree_list)
	fi= open('scripts/template.txt')
	template = Template(fi.read())
	with open('../' + md_file, "w") as f:
		f.write(template.render(title=title, date=datetime.today().strftime('%Y-%m-%d'), res_tree=tree_list, origin_info=origin_info, trans_info=trans_info, status=stat))

def is_untracking_file(commit, file_dir):
	return file_dir.startswith('.') or '/.' in file_dir or not (file_dir.endswith('.md') or file_dir.endswith('.markdown'))

def is_translate_dir(file_dir):
	return 'translations/' in file_dir

def get_translated_file(file_dir):
	file_path = os.path.dirname(file_dir) + '/translations/' + os.path.basename(file_dir).replace('.', '.ko.')
	if os.path.exists(file_path):
		return file_path
	else:
		return None

def main(commit1, commit2, md_file, settings):
	by_dir = settings['document']['translate-by'] == 'dir'

	files = git_info.get_files(commit1)
	mod = {}
	if not by_dir: 
		files += git_info.get_files(commit2)
		files = list(dict.fromkeys(files))
		m_files = git_info.get_diff_files(commit1, commit2)
	
		for f in m_files:
			mod[f[1]] = {'state': f[0], 'name': f[1]}
			if mod[f[1]]['state'] == 'R':
				mod[f[1]]['newname'] = f[2]

	tree = dtree()
	file_stat = {'Added': 0, 'Modified': 0, 'Deleted': 0, 'Renamed': 0, '-': 0}

	
	for f in files:
		f_dir = f.split('/')
		diff = {'mod': False,
			'dir': f,
			'name': f.split('/')[-1],
			'state': '-'}
		if is_untracking_file(commit2, f) or is_translate_dir(f):
			continue
		if by_dir:
			diff = get_diff(commit1, commit2, {'name': f, 'state': '-'}, False)
			file_stat[diff['state']] += 1
		elif f in mod:
			diff = get_diff(commit1, commit2, mod[f])
			file_stat[diff['state']] += 1
		leaf = get_leaf(tree, f_dir)
		leaf['/data/'] = diff

	if os.path.exists('../' + md_file):
		ran_num = 1
		while os.path.exists('../' + md_file.replace('.', f'({ran_num}).')):
			ran_num += 1
		render_page(settings['document']['title'] + f' ({ran_num})', tree, commit1, commit2, md_file.replace('.', f'({ran_num}).'), file_stat, not by_dir)
	else:
		render_page(settings['document']['title'], tree, commit1, commit2, md_file, file_stat, not by_dir)


if __name__ == '__main__':
	with open('settings.yml') as f:
		settings = yaml.load(f, yaml.FullLoader)
	translate = Translate()
	translate.set_api_key(settings['keys']['translate-api'])

	main(sys.argv[1], sys.argv[2], sys.argv[3], settings)
	translate.save_translate_cache()