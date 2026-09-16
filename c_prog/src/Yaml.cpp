#include "Yaml.hpp"

#include <cstdlib>
#include <fstream>
#include <sstream>

namespace novex
{

namespace
{

std::string stripComment(const std::string& line)
{
    bool inSingle = false;
    bool inDouble = false;

    for (size_t i = 0; i < line.size(); ++i)
    {
        const char c = line[i];

        if (c == '\'' && !inDouble)
        {
            inSingle = !inSingle;
        }
        else if (c == '"' && !inSingle)
        {
            inDouble = !inDouble;
        }
        else if (c == '#' && !inSingle && !inDouble)
        {
            return line.substr(0, i);
        }
    }

    return line;
}

std::string trim(const std::string& text)
{
    size_t begin = text.find_first_not_of(" \t\r\n");

    if (begin == std::string::npos)
    {
        return "";
    }

    size_t end = text.find_last_not_of(" \t\r\n");

    return text.substr(begin, end - begin + 1);
}

std::string unquote(const std::string& text)
{
    if (text.size() >= 2)
    {
        const char first = text.front();
        const char last  = text.back();

        if ((first == '\'' && last == '\'') ||
            (first == '"'  && last == '"'))
        {
            return text.substr(1, text.size() - 2);
        }
    }

    return text;
}

int indentOf(const std::string& line)
{
    int indent = 0;

    while (indent < static_cast<int>(line.size()) &&
           line[indent] == ' ')
    {
        ++indent;
    }

    return indent;
}

} // namespace

bool Yaml::loadFile(const std::string& path)
{
    std::ifstream file(path);

    if (!file.is_open())
    {
        errorMessage = "cannot open '" + path + "'";
        return false;
    }

    std::stringstream buffer;
    buffer << file.rdbuf();

    if (!loadString(buffer.str()))
    {
        errorMessage = path + ": " + errorMessage;
        return false;
    }

    return true;
}

bool Yaml::loadString(const std::string& text)
{
    scalars.clear();
    sequences.clear();
    errorMessage.clear();

    // Stack of (indent, key) describing the current nesting.
    std::vector<std::pair<int, std::string>> stack;

    std::string lastKeyPath;

    std::istringstream stream(text);
    std::string rawLine;

    int lineNumber = 0;

    while (std::getline(stream, rawLine))
    {
        ++lineNumber;

        const std::string line = stripComment(rawLine);
        const std::string body = trim(line);

        if (body.empty())
        {
            continue;
        }

        // A document separator is harmless; nothing else at column 0
        // that is not a key is expected.
        if (body == "---" || body == "...")
        {
            continue;
        }

        const int indent = indentOf(line);

        if (body.size() >= 2 && body[0] == '-' && body[1] == ' ')
        {
            if (lastKeyPath.empty())
            {
                errorMessage = "line " + std::to_string(lineNumber) +
                               ": sequence item with no key";
                return false;
            }

            const std::string item = unquote(trim(body.substr(2)));

            char* parseEnd = nullptr;

            const double value = std::strtod(item.c_str(), &parseEnd);

            if (parseEnd == item.c_str())
            {
                errorMessage = "line " + std::to_string(lineNumber) +
                               ": only numeric sequences are supported"
                               " (got '" + item + "')";
                return false;
            }

            sequences[lastKeyPath].push_back(value);
            continue;
        }

        const size_t colon = body.find(':');

        if (colon == std::string::npos)
        {
            errorMessage = "line " + std::to_string(lineNumber) +
                           ": expected 'key: value'";
            return false;
        }

        const std::string key = trim(body.substr(0, colon));
        const std::string value = trim(body.substr(colon + 1));

        while (!stack.empty() && stack.back().first >= indent)
        {
            stack.pop_back();
        }

        std::string path;

        for (const auto& level : stack)
        {
            path += level.second;
            path += '.';
        }

        path += key;

        if (value.empty() || value == "{}" || value == "[]")
        {
            // Either a nested block or an explicitly empty collection.
            // Both are represented by pushing the key; an empty
            // collection simply never gets children.
            stack.emplace_back(indent, key);
            lastKeyPath = path;
        }
        else
        {
            scalars[path] = unquote(value);
            lastKeyPath = path;
        }
    }

    return true;
}

bool Yaml::has(const std::string& key) const
{
    return scalars.count(key) > 0 || sequences.count(key) > 0;
}

std::string Yaml::getString(const std::string& key,
                            const std::string& fallback) const
{
    auto it = scalars.find(key);

    return (it == scalars.end()) ? fallback : it->second;
}

double Yaml::getDouble(const std::string& key, double fallback) const
{
    auto it = scalars.find(key);

    if (it == scalars.end())
    {
        return fallback;
    }

    char* parseEnd = nullptr;

    const double value = std::strtod(it->second.c_str(), &parseEnd);

    return (parseEnd == it->second.c_str()) ? fallback : value;
}

int Yaml::getInt(const std::string& key, int fallback) const
{
    const double value = getDouble(key, static_cast<double>(fallback));

    return static_cast<int>(value);
}

bool Yaml::getBool(const std::string& key, bool fallback) const
{
    auto it = scalars.find(key);

    if (it == scalars.end())
    {
        return fallback;
    }

    const std::string& value = it->second;

    if (value == "true"  || value == "True"  ||
        value == "yes"   || value == "on"    || value == "1")
    {
        return true;
    }

    if (value == "false" || value == "False" ||
        value == "no"    || value == "off"   || value == "0")
    {
        return false;
    }

    return fallback;
}

std::vector<double> Yaml::getVector(const std::string& key) const
{
    auto it = sequences.find(key);

    return (it == sequences.end())
        ? std::vector<double>()
        : it->second;
}

} // namespace novex
