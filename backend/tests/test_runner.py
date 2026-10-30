"""The code runner: every language, every verdict, and the limits.

    python -m unittest backend.tests.test_runner -v
"""
import unittest

from backend.services import runner

SUM = {   # read two numbers, print the sum
    "python": "a, b = map(int, input().split())\nprint(a + b)\n",
    "cpp": "#include <bits/stdc++.h>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b<<\"\\n\";}\n",
    "java": "import java.util.*;\npublic class Main{public static void main(String[] x){Scanner s=new Scanner(System.in);"
            "long a=s.nextLong(),b=s.nextLong();System.out.println(a+b);}}\n",
    "javascript": "const [a,b]=require('fs').readFileSync(0,'utf8').trim().split(/\\s+/).map(Number);console.log(a+b);\n",
}
TESTS = [dict(input="2 3\n", expected="5\n"), dict(input="-7 7", expected="0"), dict(input="1000000000 1000000000\n", expected="2000000000")]
AV = runner.available()


class Runner(unittest.TestCase):
    def test_accepted_every_language(self):
        for lang, code in SUM.items():
            if not AV[lang]:
                print(f"  skip {lang}: not installed")
                continue
            v = runner.judge(lang, code, TESTS, time_limit=2, show=True)
            self.assertEqual((v.verdict, v.passed, v.total), ("accepted", 3, 3), (lang, v))
            print(f"  {lang:<10} accepted in {v.seconds:.2f} s")

    def test_wrong_answer_shows_samples_only_when_asked(self):
        v = runner.judge("python", "print(5)\n", TESTS, time_limit=2, show=True)
        self.assertEqual((v.verdict, v.passed), ("wrong_answer", 1))
        self.assertEqual(v.tests[1]["output"].strip(), "5")
        hidden = runner.judge("python", "print(5)\n", TESTS, time_limit=2, show=False)
        self.assertNotIn("input", hidden.tests[0])                 # hidden tests never return data

    def test_compile_errors(self):
        self.assertEqual(runner.judge("python", "print(\n", TESTS, 2, True).verdict, "runtime_error")   # Python: at run time
        for lang, bad in (("cpp", "int main( {"), ("java", "public class Main { void x( }")):
            if AV[lang]:
                v = runner.judge(lang, bad, TESTS, 2, True)
                self.assertEqual(v.verdict, "compile_error", lang)
                self.assertNotIn("/tmp/", v.compile_output)

    def test_runtime_error(self):
        v = runner.judge("python", "raise SystemExit(3)\n", TESTS[:1], 2, True)
        self.assertEqual(v.verdict, "runtime_error")
        if AV["cpp"]:
            self.assertEqual(runner.judge("cpp", "int main(){int*p=0;return *p;}", TESTS[:1], 2, True).verdict, "runtime_error")

    def test_time_limit(self):
        for lang, code in (("python", "while True: pass\n"), ("cpp", "int main(){volatile long x=0;for(;;)x++;}"),
                           ("java", "public class Main{public static void main(String[] a){long x=0;while(true)x++;}}"),
                           ("javascript", "for(;;){}")):
            if AV[lang]:
                v = runner.judge(lang, code, TESTS[:1], time_limit=1, show=True)
                self.assertEqual(v.verdict, "time_limit", (lang, v))
                self.assertLess(v.seconds, 8, lang)

    def test_output_flood_and_memory(self):
        self.assertEqual(runner.judge("python", "while True: print('x' * 1000)\n", TESTS[:1], 2, True).verdict, "output_limit")
        v = runner.judge("python", "a = bytearray(1024 * 1024 * 1024)\nprint(len(a))\n", TESTS[:1], 2, True)
        self.assertEqual(v.verdict, "runtime_error", v)

    def test_cannot_write_big_files_or_read_env(self):
        v = runner.run_custom("python", "import os\nprint(os.environ.get('FP_JWT_SECRET', 'none'), os.environ.get('DATABASE_URL', 'none'))\n", "", 2)
        self.assertEqual(v["output"].strip(), "none none")

    def test_custom_input(self):
        r = runner.run_custom("python", SUM["python"], "40 2", 2)
        self.assertEqual((r["status"], r["output"].strip()), ("ok", "42"))

    def test_normalise(self):
        self.assertEqual(runner.normalise("1 \r\n2\n\n\n"), runner.normalise("1\n2"))


if __name__ == "__main__":
    unittest.main()
