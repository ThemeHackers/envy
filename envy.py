import os
import pathlib
import pprint
import re
import itertools
import glob
import functools
from concurrent.futures import ThreadPoolExecutor
import time
import argparse
from colorama import init, Fore, Style, Back
import sys
from tqdm import tqdm

# Initialize colorama
init()

parser = argparse.ArgumentParser(description="Find environment variable-based paths and generate glob patterns")
parser.add_argument("target", help="Target path to analyze")
parser.add_argument("--all", action="store_true", help="Show all possible matches instead of just the shortest")
args = parser.parse_args()

# Cache for glob results
glob_cache = {}
path_cache = {}

@functools.lru_cache(maxsize=1024)
def test_if_env_matches(test, target):
    regex_string = rf'^{test.replace("?",".").replace("*",".*")}$'
    matches = []
    for key in os.environ.keys():
        match = re.search(regex_string, key)
        if match:
            matches.append(match.group())
    return len(matches) == 1 and target in matches

@functools.lru_cache(maxsize=1024)
def test_if_glob_matches(test, start_path, target):
    if start_path not in glob_cache:
        glob_cache[start_path] = glob.glob(os.path.join(start_path, "*"))
    matches = [p for p in glob_cache[start_path] if pathlib.Path(p).match(test)]
    return len(matches) == 1 and target in matches

@functools.lru_cache(maxsize=1024)
def glob_mutate(subpath):
    mutations = []
    for each_possibility in itertools.product("?X", repeat=len(subpath)):
        new_mutation = list(each_possibility)
        for i, c in enumerate(each_possibility):
            if c == "X":
                new_mutation[i] = subpath[i]
        mutations.append("".join(new_mutation))
    return mutations

@functools.lru_cache(maxsize=1024)
def star_replace(subpath_mutation):
    return re.sub(r"\?+", "*", subpath_mutation)

@functools.lru_cache(maxsize=1024)
def path_parts(path_str):
    return tuple(piece.rstrip("\\") for piece in pathlib.Path(path_str).parts)

def process_env_matches(env_key, target_parts, env_parts):
    env_matches = []
    left_over_parts = target_parts[len(env_parts):]
    for to_test in glob_mutate(env_key):
        if test_if_env_matches(to_test, env_key):
            env_matches.append(to_test)
    return env_matches

def process_glob_mutations(env, remaining_part, each_part, base_path, full_path):
    question_mark_mutations = []
    for each_question_mark_mutation in glob_mutate(each_part):
        question_mark_mutation_path = os.path.join(env, remaining_part, each_question_mark_mutation)
        if test_if_glob_matches(question_mark_mutation_path, base_path, full_path):
            question_mark_mutations.append(each_question_mark_mutation)
    
    star_mutation_matches = []
    max_length = 10000
    for each_mutation in question_mark_mutations:
        star_mutation = star_replace(each_mutation)
        star_mutation_path = os.path.join(env, remaining_part, star_mutation)
        if len(star_mutation) >= max_length:
            continue
        if star_mutation not in star_mutation_matches:
            if test_if_glob_matches(star_mutation_path, base_path, full_path):
                if max_length == 0:
                    max_length = len(star_mutation)
                max_length = len(star_mutation)
                star_mutation_matches.append(star_mutation)
    return question_mark_mutations + star_mutation_matches

def print_header(text):
    width = 80
    print(f"\n{Fore.CYAN}{'╔' + '═' * (width-2) + '╗'}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}║{text:^{width-2}}║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'╚' + '═' * (width-2) + '╝'}{Style.RESET_ALL}\n")

def print_section(text):
    width = 80
    print(f"\n{Fore.YELLOW}{'╭' + '─' * (width-2) + '╮'}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}│ {text}{' ' * (width-4-len(text))}│{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{'╰' + '─' * (width-2) + '╯'}{Style.RESET_ALL}")

def print_path(path):
    parts = path.split(os.path.sep)
    colored_parts = []
    for part in parts:
        if part.startswith("$env:"):
            colored_parts.append(f"{Fore.GREEN}{Back.BLACK}{part}{Style.RESET_ALL}")
        elif "*" in part or "?" in part:
            colored_parts.append(f"{Fore.MAGENTA}{Back.BLACK}{part}{Style.RESET_ALL}")
        else:
            colored_parts.append(f"{Fore.WHITE}{Back.BLACK}{part}{Style.RESET_ALL}")
    return f"{Fore.WHITE}{Back.BLACK}{os.path.sep.join(colored_parts)}{Style.RESET_ALL}"

def print_progress(text):
    sys.stdout.write(f"\r{Fore.YELLOW}⏳ {text}{' ' * 20}{Style.RESET_ALL}")
    sys.stdout.flush()

def print_success(text):
    print(f"{Fore.GREEN}✓ {text}{Style.RESET_ALL}")

def print_error(text):
    print(f"{Fore.RED}✗ {text}{Style.RESET_ALL}")

def print_info(text):
    print(f"{Fore.BLUE}ℹ {text}{Style.RESET_ALL}")

def print_summary_box(title, content):
    width = 80
    print(f"\n{Fore.CYAN}{'╔' + '═' * (width-2) + '╗'}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}║ {title}{' ' * (width-4-len(title))}║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'╠' + '═' * (width-2) + '╣'}{Style.RESET_ALL}")
    for line in content:
        print(f"{Fore.CYAN}║ {line}{' ' * (width-4-len(line))}║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'╚' + '═' * (width-2) + '╝'}{Style.RESET_ALL}\n")

def main():
    global glob_cache, args
    
    start_time = time.time()
    target = args.target
    target_norm_str = os.path.normpath(target)
    target_path = pathlib.Path(target_norm_str)
    
    if not target_path.is_absolute():
        print_error("Absolute path required")
        return
        
    print_header("ENVY - Environment Variable Path Analyzer")
    print_section("Analyzing Path")
    print_info(f"Target path: {target}")
    
    env_score = {}
    target_parts = path_parts(target_norm_str)
    
    # Pre-calculate environment paths
    env_paths = {k: os.path.normpath(v) for k, v in os.environ.items() 
                if os.path.exists(v) and os.path.isdir(v)}
    
    print_section("Processing Environment Variables")
    print_progress("Scanning environment variables...")
    
    # Score environment variables in parallel
    with ThreadPoolExecutor() as executor:
        futures = []
        for env_key, value_path in env_paths.items():
            value_path_parts = path_parts(value_path)
            if len(value_path_parts) <= len(target_parts):
                futures.append(executor.submit(process_env_score, env_key, value_path_parts, target_parts))
        
        for future in futures:
            env_key, score = future.result()
            if score > 0:
                env_score[env_key] = score
    
    if not env_score:
        print_error("No matching environment variables found")
        return
        
    highest_score_env = max(env_score, key=env_score.get)
    highest_score_value = env_score[highest_score_env]
    best_envs = [key for key, value in env_score.items() if value == highest_score_value]

    print_success(f"Found {len(best_envs)} matching environment variables")
    
    print_section("Generating Path Patterns")
    print_progress("Processing environment matches...")
    
    # Process environment matches in parallel
    with ThreadPoolExecutor() as executor:
        futures = []
        for env_key in best_envs:
            env = os.path.normpath(os.environ[env_key])
            env_parts = path_parts(env)
            futures.append(executor.submit(process_env_matches, env_key, target_parts, env_parts))
        
        starting_matches = [future.result() for future in futures]
    
    env = os.path.normpath(os.environ[best_envs[0]])
    env_parts = path_parts(env)
    left_over_parts = target_parts[len(env_parts):]
    
    print_progress("Caching subdirectories...")
    # Pre-cache glob results
    with ThreadPoolExecutor() as executor:
        futures = []
        for i, subpart in enumerate(left_over_parts):
            map_path = os.path.join(env, os.path.sep.join(left_over_parts[:i]))
            futures.append(executor.submit(glob.glob, os.path.join(map_path, "*")))
        
        for i, future in enumerate(futures):
            map_path = os.path.join(env, os.path.sep.join(left_over_parts[:i]))
            glob_cache[map_path] = future.result()
    
    print_progress(f"Finding glob patterns for '{target}'...")
    # Process glob mutations in parallel
    with ThreadPoolExecutor() as executor:
        futures = []
        for i, each_part in enumerate(left_over_parts):
            remaining_part = os.path.sep.join(left_over_parts[:i])
            base_path = os.path.join(env, remaining_part)
            full_path = os.path.join(env, remaining_part, each_part)
            futures.append(executor.submit(process_glob_mutations, env, remaining_part, each_part, base_path, full_path))
        
        remaining_matches = [future.result() for future in futures]
    
    print_section("Results")
    shortest = 0
    all_options = []
    
    for env_starts in starting_matches:
        for start in env_starts:
            for every_option in itertools.product(*remaining_matches):
                new_option = f"$env:{start}{os.path.sep}{os.path.sep.join(every_option)}"
                if args.all:
                    print(print_path(new_option))
                else:
                    if shortest == 0:
                        shortest = len(new_option)
                    if len(new_option) < shortest:
                        print(print_path(new_option))
                        shortest = len(new_option)
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    summary_content = [
        f"Target Path: {target}",
        f"Execution Time: {execution_time:.2f} seconds",
        f"Environment Variables Found: {len(best_envs)}",
        f"Shortest Path Length: {shortest} characters"
    ]
    
    print_summary_box("Analysis Summary", summary_content)

def process_env_score(env_key, value_path_parts, target_parts):
    score = 0
    for i, part in enumerate(value_path_parts):
        if target_parts[i] == value_path_parts[i]:
            score += 1
        else:
            score = 0
            break
    return env_key, score

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[!] Program interrupted by user{Style.RESET_ALL}")
        exit(0)
    except Exception as e:
        print(f"\n{Fore.RED}[!] An error occurred: {str(e)}{Style.RESET_ALL}")
        exit(1)
    
